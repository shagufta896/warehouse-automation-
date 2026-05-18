"""
Advanced data preprocessing pipeline for inventory forecasting.
Handles: missing values, outlier detection, duplicate removal,
         abnormal spikes, normalization, and feature engineering
         for Indian FMCG market patterns.
"""
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ── Indian Public Holidays & Festivals (approximate annual dates) ──────────
INDIAN_FESTIVALS = {
    # Month-Day -> festival name (recurring approximations)
    (1, 14): "Makar Sankranti",
    (1, 26): "Republic Day",
    (3, 25): "Holi",       # approximate
    (4, 14): "Baisakhi",
    (8, 15): "Independence Day",
    (8, 26): "Janmashtami",  # approximate
    (10, 2): "Gandhi Jayanti",
    (10, 15): "Navratri",    # approximate
    (10, 24): "Dussehra",    # approximate
    (11, 1):  "Diwali",      # approximate
    (11, 12): "Diwali",      # alternate years
    (12, 25): "Christmas",
}

FESTIVAL_WINDOW_DAYS = 3  # days before/after festival to mark as "festival period"


def _is_festival_period(date: pd.Timestamp) -> bool:
    """Check if a date falls within a festival window."""
    for (m, d), name in INDIAN_FESTIVALS.items():
        festival_date = pd.Timestamp(year=date.year, month=m, day=d)
        if abs((date - festival_date).days) <= FESTIVAL_WINDOW_DAYS:
            return True
    return False


def _get_festival_name(date: pd.Timestamp) -> str:
    """Return festival name if within window, else empty string."""
    for (m, d), name in INDIAN_FESTIVALS.items():
        festival_date = pd.Timestamp(year=date.year, month=m, day=d)
        if abs((date - festival_date).days) <= FESTIVAL_WINDOW_DAYS:
            return name
    return ""


def _get_season_india(month: int) -> str:
    """Map month to Indian season."""
    if month in [12, 1, 2]:    return "Winter"
    if month in [3, 4, 5]:     return "Summer"
    if month in [6, 7, 8, 9]:  return "Monsoon"
    return "Post-Monsoon"       # Oct, Nov


# ── Main Preprocessing Pipeline ───────────────────────────────────────────
def preprocess_sales_dataframe(df: pd.DataFrame, min_days: int = 7) -> pd.DataFrame:
    """
    Full preprocessing pipeline for ML-ready sales data.

    Input df must have columns: ds (datetime), y (units sold)
    Returns cleaned, feature-enriched DataFrame.

    Steps:
      1. Type coercion & date parsing
      2. Duplicate removal
      3. Missing date gap filling
      4. Outlier / spike detection and capping
      5. Negative value correction
      6. Indian festival & seasonal features
      7. Calendar features
      8. Lag & rolling window features
      9. Minimum data validation
    """
    if df.empty:
        raise ValueError("Input dataframe is empty.")

    df = df.copy()

    # ── 1. Type coercion ────────────────────────────────────────────────
    df['ds'] = pd.to_datetime(df['ds'], errors='coerce')
    df['y'] = pd.to_numeric(df['y'], errors='coerce').astype(float)
    df.dropna(subset=['ds', 'y'], inplace=True)
    df.sort_values('ds', inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger.info(f"Preprocessing: {len(df)} raw rows")

    # ── 2. Duplicate dates — keep last entry ────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset='ds', keep='last')
    if len(df) < before:
        logger.info(f"Removed {before - len(df)} duplicate date rows")

    # ── 3. Fill missing date gaps with 0 ────────────────────────────────
    full_range = pd.date_range(start=df['ds'].min(), end=df['ds'].max(), freq='D')
    df = df.set_index('ds').reindex(full_range).rename_axis('ds').reset_index()
    df['y'] = df['y'].fillna(0)
    logger.info(f"After gap-filling: {len(df)} rows")

    # ── 4. Outlier detection (IQR + Z-score hybrid) ─────────────────────
    q1 = df['y'].quantile(0.25)
    q3 = df['y'].quantile(0.75)
    iqr = q3 - q1
    iqr_upper = q3 + 3.0 * iqr   # lenient — 3× IQR for retail spikes

    z_scores = np.abs((df['y'] - df['y'].mean()) / (df['y'].std() + 1e-9))
    outlier_mask = (df['y'] > iqr_upper) & (z_scores > 3.5)
    outlier_count = outlier_mask.sum()
    if outlier_count > 0:
        cap_value = df['y'].quantile(0.95)
        df.loc[outlier_mask, 'y'] = cap_value
        logger.info(f"Capped {outlier_count} outlier spikes at p95={cap_value:.1f}")

    # ── 5. Negative sales correction ────────────────────────────────────
    df['y'] = df['y'].clip(lower=0)

    # ── 6. Indian festival features ─────────────────────────────────────
    df['is_festival'] = df['ds'].apply(_is_festival_period).astype(int)
    df['festival_name'] = df['ds'].apply(_get_festival_name)
    df['season'] = df['ds'].dt.month.apply(_get_season_india)

    # ── 7. Calendar features ────────────────────────────────────────────
    df['day_of_week']    = df['ds'].dt.dayofweek          # 0=Mon
    df['day_of_month']   = df['ds'].dt.day
    df['month']          = df['ds'].dt.month
    df['quarter']        = df['ds'].dt.quarter
    df['week_of_year']   = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend']     = (df['day_of_week'] >= 5).astype(int)
    df['is_month_start'] = df['ds'].dt.is_month_start.astype(int)
    df['is_month_end']   = df['ds'].dt.is_month_end.astype(int)
    df['is_month_15']    = (df['ds'].dt.day == 15).astype(int)  # salary bump

    # Indian pay-cycle boost: 1st week and 15th–31st day of month
    df['is_payday_window'] = (
        (df['ds'].dt.day <= 5) | (df['ds'].dt.day >= 25)
    ).astype(int)

    # ── 8. Lag + rolling window features (only if enough data) ──────────
    n = len(df)
    if n >= 7:
        df['lag_1']           = df['y'].shift(1)
        df['lag_7']           = df['y'].shift(7)
        df['rolling_mean_7']  = df['y'].rolling(7,  min_periods=1).mean()
        df['rolling_std_7']   = df['y'].rolling(7,  min_periods=1).std().fillna(0)
    if n >= 14:
        df['lag_14']          = df['y'].shift(14)
        df['rolling_mean_14'] = df['y'].rolling(14, min_periods=1).mean()
    if n >= 30:
        df['lag_30']          = df['y'].shift(30)
        df['rolling_mean_30'] = df['y'].rolling(30, min_periods=1).mean()

    # Fill lag NaNs with rolling mean
    lag_cols = [c for c in df.columns if c.startswith('lag_') or c.startswith('rolling_')]
    df[lag_cols] = df[lag_cols].fillna(df['y'].mean())

    # ── 9. Minimum data guard ───────────────────────────────────────────
    unique_days = df['y'].gt(0).sum()
    if unique_days < min_days:
        raise ValueError(
            f"Only {unique_days} days with sales data found. "
            f"Need at least {min_days} days to generate predictions."
        )

    logger.info(
        f"Preprocessing complete: {len(df)} rows, "
        f"{unique_days} days with sales, "
        f"{int(df['is_festival'].sum())} festival days"
    )
    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    """Return the feature columns present in a preprocessed dataframe."""
    base = [
        'day_of_week', 'day_of_month', 'month', 'quarter', 'week_of_year',
        'is_weekend', 'is_month_start', 'is_month_end', 'is_month_15',
        'is_payday_window', 'is_festival',
    ]
    lag_cols = [c for c in df.columns if c.startswith('lag_') or c.startswith('rolling_')]
    return [c for c in base + lag_cols if c in df.columns]


def load_dataset(file_path: str) -> pd.DataFrame:
    """Load a CSV dataset."""
    return pd.read_csv(file_path)


def filter_product_data(df: pd.DataFrame, product_name: str) -> pd.DataFrame:
    """Filter a raw dataset to a single product and return ds/y frame."""
    product_df = df[df["Product_Name"] == product_name]
    forecast_df = product_df[["Date", "Units_Sold"]].copy()
    forecast_df.columns = ["ds", "y"]
    forecast_df["ds"] = pd.to_datetime(forecast_df["ds"])
    return forecast_df
