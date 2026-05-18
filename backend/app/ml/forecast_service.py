"""
Forecast service: generates demand predictions using best-trained model.
Supports as few as 7 days of sales history with graceful fallbacks.
"""
from sqlalchemy.orm import Session
from app.database.crud import SalesHistoryCRUD, ForecastCRUD, ProductCRUD
from app.ml.train_model import ForecastModelTrainer
from app.ml.preprocess import preprocess_sales_dataframe, get_feature_columns, _get_season_india, _is_festival_period
from typing import List, Dict
import logging, pandas as pd, numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _safe_int(value) -> int:
    if isinstance(value, bytes):
        return int.from_bytes(value, byteorder='little', signed=True)
    return int(value) if value is not None else 0


def _build_future_features(df_clean: pd.DataFrame, last_date: pd.Timestamp, days: int) -> pd.DataFrame:
    """Build feature rows for future dates using the preprocessed history."""
    future_rows = []
    for i in range(1, days + 1):
        date = last_date + timedelta(days=i)
        from app.ml.preprocess import _get_festival_name, INDIAN_FESTIVALS
        row = {
            'ds': date,
            'day_of_week':    date.dayofweek,
            'day_of_month':   date.day,
            'month':          date.month,
            'quarter':        (date.month - 1) // 3 + 1,
            'week_of_year':   date.isocalendar().week,
            'is_weekend':     int(date.dayofweek >= 5),
            'is_month_start': int(date.day == 1),
            'is_month_end':   int(date.day >= 28),
            'is_month_15':    int(date.day == 15),
            'is_payday_window': int(date.day <= 5 or date.day >= 25),
            'is_festival':    int(_is_festival_period(pd.Timestamp(date))),
        }
        # Lag features from history tail
        n = len(df_clean)
        row['lag_1']           = float(df_clean['y'].iloc[-1]) if n >= 1 else 0
        row['lag_7']           = float(df_clean['y'].iloc[-7]) if n >= 7 else float(df_clean['y'].mean())
        row['lag_14']          = float(df_clean['y'].iloc[-14]) if n >= 14 else float(df_clean['y'].mean())
        row['lag_30']          = float(df_clean['y'].iloc[-30]) if n >= 30 else float(df_clean['y'].mean())
        row['rolling_mean_7']  = float(df_clean['y'].tail(7).mean())
        row['rolling_std_7']   = float(df_clean['y'].tail(7).std() or 0)
        row['rolling_mean_14'] = float(df_clean['y'].tail(14).mean())
        row['rolling_mean_30'] = float(df_clean['y'].tail(30).mean()) if n >= 30 else row['rolling_mean_14']
        future_rows.append(row)
    return pd.DataFrame(future_rows)


def generate_forecast(db: Session, product_name: str, days: int = 30) -> Dict:
    """
    Generate demand forecast for a product.
    Works with as few as 7 days of sales history.
    """
    # Validate product
    product = ProductCRUD.get_product_by_name(db, product_name)
    if not product:
        raise ValueError(f"Product '{product_name}' not found in database")

    # Load raw sales history
    df_raw = SalesHistoryCRUD.get_sales_dataframe(db, product_name)
    if df_raw.empty:
        raise ValueError(f"No sales data found for '{product_name}'. Upload a CSV or add manual entries first.")

    # Preprocess (raises ValueError if < 7 days)
    df_clean = preprocess_sales_dataframe(df_raw, min_days=7)
    n_days = len(df_clean)

    trainer = ForecastModelTrainer()

    # Try loading cached model; retrain if stale or missing
    try:
        model_data = trainer.load_models(product_name)
        logger.info(f"Loaded cached model for '{product_name}'")
    except (FileNotFoundError, Exception) as e:
        logger.info(f"No cached model (reason: {e}) — training for '{product_name}'")
        model_data = trainer.train_and_save(df_raw, product_name)

    best_name = model_data['best_model']
    model     = model_data['models'][best_name]['model']
    metrics   = model_data['models'][best_name]['metrics']

    last_date = df_clean['ds'].max()
    predictions = []

    # ── Prophet prediction ────────────────────────────────────────────
    if best_name == 'prophet':
        future = model.make_future_dataframe(periods=days)
        forecast = model.predict(future)
        tail = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days).copy()
        # Sanitize NaN/Inf before clipping (multiplicative mode can produce these)
        tail['yhat']       = tail['yhat'].replace([np.inf, -np.inf], 0).fillna(0)
        tail['yhat_lower'] = tail['yhat_lower'].replace([np.inf, -np.inf], 0).fillna(0)
        tail['yhat_upper'] = tail['yhat_upper'].replace([np.inf, -np.inf], 0).fillna(0)
        tail['yhat']       = tail['yhat'].clip(lower=0).round(2)
        tail['yhat_lower'] = tail['yhat_lower'].clip(lower=0).round(2)
        tail['yhat_upper'] = tail['yhat_upper'].clip(lower=0).round(2)
        tail['ds']         = tail['ds'].dt.strftime('%Y-%m-%d')
        predictions = tail.to_dict(orient='records')

    # ── ML model prediction ───────────────────────────────────────────
    else:
        future_df = _build_future_features(df_clean, last_date, days)
        feature_cols = get_feature_columns(df_clean)
        # Only use columns the model was trained on
        available = [c for c in feature_cols if c in future_df.columns]
        X_future = future_df[available].fillna(0)

        try:
            y_pred = model.predict(X_future)
        except Exception as e:
            logger.error(f"Model prediction failed: {e}, falling back to rolling mean")
            mean_val = float(df_clean['y'].tail(14).mean())
            y_pred = np.full(days, mean_val)

        y_pred = np.clip(y_pred, 0, None)
        std = float(df_clean['y'].std() or 1)
        for i, (_, row) in enumerate(future_df.iterrows()):
            yhat = round(float(y_pred[i]), 2)
            predictions.append({
                'ds':         row['ds'].strftime('%Y-%m-%d'),
                'yhat':       yhat,
                'yhat_lower': round(max(0, yhat - std), 2),
                'yhat_upper': round(yhat + std, 2),
            })

    # Save to DB cache
    try:
        ForecastCRUD.save_forecast(db, product.product_id, predictions, best_name)
    except Exception as e:
        logger.warning(f"Could not cache forecast: {e}")

    # Include all model metrics for comparison
    all_metrics = {
        name: info['metrics']
        for name, info in model_data['models'].items()
    }

    return {
        'predictions':  predictions,
        'model_used':   best_name,
        'metrics':      metrics,
        'all_metrics':  all_metrics,
        'data_points':  n_days,
    }


def get_all_products_list(db: Session) -> List[Dict]:
    """Get list of all available products."""
    products = ProductCRUD.get_all_products(db)
    return [
        {
            'product_id':    str(p.product_id) if p.product_id is not None else '',
            'product_name':  str(p.product_name) if p.product_name is not None else '',
            'category':      str(p.category) if p.category is not None else '',
            'current_stock': _safe_int(p.current_stock),
            'reorder_point': _safe_int(p.reorder_point),
        }
        for p in products
    ]
