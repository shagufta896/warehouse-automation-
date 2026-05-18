"""
ML model training: Prophet + XGBoost + Random Forest + Gradient Boosting
with Indian market features, automatic model selection by MAE.
"""
from prophet import Prophet
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error
import numpy as np
import pandas as pd
import joblib
import os
from datetime import datetime
import logging
from config import settings
from app.ml.preprocess import preprocess_sales_dataframe, get_feature_columns, INDIAN_FESTIVALS

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("XGBoost not installed — skipping XGB model")


class ForecastModelTrainer:
    """Train and evaluate forecasting models with Indian market features."""

    def __init__(self):
        self.model_dir = settings.MODEL_FOLDER
        os.makedirs(self.model_dir, exist_ok=True)

    # ── Feature preparation ────────────────────────────────────────────
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run full preprocessing pipeline (includes lag/festival features)."""
        return preprocess_sales_dataframe(df, min_days=7)

    def _feature_cols(self, df: pd.DataFrame) -> list:
        return get_feature_columns(df)

    # ── Prophet ───────────────────────────────────────────────────────
    def train_prophet_model(self, df: pd.DataFrame, product_name: str) -> Prophet:
        logger.info(f"Training Prophet for {product_name}")
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode='multiplicative',
            changepoint_prior_scale=0.05,
        )

        # Add Indian holiday regressors
        holidays = []
        for year in range(df['ds'].dt.year.min(), df['ds'].dt.year.max() + 2):
            for (m, d), name in INDIAN_FESTIVALS.items():
                try:
                    holidays.append({'holiday': name, 'ds': pd.Timestamp(year=year, month=m, day=d),
                                     'lower_window': -2, 'upper_window': 2})
                except Exception:
                    pass
        if holidays:
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                seasonality_mode='multiplicative',
                changepoint_prior_scale=0.05,
                holidays=pd.DataFrame(holidays),
            )

        model.fit(df[['ds', 'y']])
        return model

    # ── XGBoost ───────────────────────────────────────────────────────
    def train_xgboost_model(self, df: pd.DataFrame) -> object:
        if not XGB_AVAILABLE:
            return None
        feature_cols = self._feature_cols(df)
        df_clean = df.dropna(subset=feature_cols + ['y'])
        if len(df_clean) < 20:
            return None
        X = df_clean[feature_cols]
        y = df_clean['y']
        split_idx = int(len(X) * 0.8)
        model = xgb.XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            objective='reg:squarederror', verbosity=0
        )
        model.fit(X[:split_idx], y[:split_idx],
                  eval_set=[(X[split_idx:], y[split_idx:])],
                  verbose=False)
        return model

    # ── Sklearn ML models ─────────────────────────────────────────────
    def train_ml_models(self, df: pd.DataFrame) -> dict:
        feature_cols = self._feature_cols(df)
        df_clean = df.dropna(subset=feature_cols + ['y'])
        if len(df_clean) < 20:
            logger.warning("Not enough data for ML models")
            return {}

        X = df_clean[feature_cols]
        y = df_clean['y']
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        models = {}

        rf = RandomForestRegressor(n_estimators=150, random_state=42, max_depth=10, n_jobs=-1)
        rf.fit(X_train, y_train)
        models['random_forest'] = rf

        gb = GradientBoostingRegressor(n_estimators=150, random_state=42, max_depth=5, learning_rate=0.05)
        gb.fit(X_train, y_train)
        models['gradient_boosting'] = gb

        return models

    # ── Evaluation ────────────────────────────────────────────────────
    def evaluate_model(self, model, df: pd.DataFrame, model_type: str = 'prophet') -> dict:
        if len(df) < 14:
            return {'mae': 0.0, 'rmse': 0.0, 'mape': 0.0}
        split_idx = int(len(df) * 0.8)
        try:
            if model_type == 'prophet':
                forecast = model.predict(df[['ds']][split_idx:])
                y_true = df['y'].values[split_idx:]
                y_pred = forecast['yhat'].values
            else:
                feature_cols = self._feature_cols(df)
                df_clean = df.dropna(subset=feature_cols)
                X_test = df_clean[feature_cols][split_idx:]
                y_true = df_clean['y'].values[split_idx:]
                y_pred = model.predict(X_test)

            y_true = np.array(y_true, dtype=float)
            y_pred = np.array(y_pred, dtype=float)
            y_pred = np.clip(y_pred, 0, None)

            mae  = mean_absolute_error(y_true, y_pred)
            rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            nonzero = y_true != 0
            mape = mean_absolute_percentage_error(y_true[nonzero], y_pred[nonzero]) * 100 if nonzero.any() else 0.0

            return {'mae': round(mae, 2), 'rmse': round(rmse, 2), 'mape': round(mape, 2)}
        except Exception as e:
            logger.warning(f"Evaluation failed for {model_type}: {e}")
            return {'mae': 0.0, 'rmse': 0.0, 'mape': 0.0}

    # ── Train + Save ──────────────────────────────────────────────────
    def train_and_save(self, df: pd.DataFrame, product_name: str) -> dict:
        logger.info(f"Starting training for '{product_name}' ({len(df)} rows)")

        # Run preprocessing
        try:
            df_clean = preprocess_sales_dataframe(df, min_days=7)
        except ValueError as e:
            raise ValueError(str(e))

        results = {
            'product_name': product_name,
            'trained_at': datetime.utcnow().isoformat(),
            'models': {},
            'best_model': None
        }

        # Prophet
        try:
            pm = self.train_prophet_model(df_clean, product_name)
            results['models']['prophet'] = {'model': pm, 'metrics': self.evaluate_model(pm, df_clean, 'prophet')}
        except Exception as e:
            logger.error(f"Prophet training failed: {e}")

        # XGBoost
        if XGB_AVAILABLE:
            try:
                xm = self.train_xgboost_model(df_clean)
                if xm:
                    results['models']['xgboost'] = {'model': xm, 'metrics': self.evaluate_model(xm, df_clean, 'xgboost')}
            except Exception as e:
                logger.error(f"XGBoost training failed: {e}")

        # Random Forest + Gradient Boosting
        try:
            for name, model in self.train_ml_models(df_clean).items():
                results['models'][name] = {'model': model, 'metrics': self.evaluate_model(model, df_clean, name)}
        except Exception as e:
            logger.error(f"ML model training failed: {e}")

        if not results['models']:
            raise RuntimeError(f"All models failed to train for '{product_name}'")

        # Select best by MAE (lowest)
        results['best_model'] = min(
            results['models'].keys(),
            key=lambda k: results['models'][k]['metrics']['mae'] or float('inf')
        )

        # Save
        safe_name = product_name.replace(' ', '_').replace('/', '_')
        path = os.path.join(self.model_dir, f"{safe_name}.pkl")
        joblib.dump(results, path)
        logger.info(f"Saved model for '{product_name}'. Best: {results['best_model']}")

        return results

    def load_models(self, product_name: str) -> dict:
        safe_name = product_name.replace(' ', '_').replace('/', '_')
        path = os.path.join(self.model_dir, f"{safe_name}.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No model for '{product_name}'")
        return joblib.load(path)
