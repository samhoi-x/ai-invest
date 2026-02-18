"""Feature engineering for ML models."""

import pandas as pd
import numpy as np
from analysis.technical import compute_all_indicators
from config import ML_PARAMS


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from OHLCV data.

    Returns a DataFrame with engineered features suitable for ML models.
    All features are numeric and NaN-free (rows with NaN are dropped).
    """
    if df.empty:
        return pd.DataFrame()

    # Start with technical indicators
    feat = compute_all_indicators(df)

    # ── Price-based features ─────────────────────────────────────────
    feat["return_1d"] = feat["close"].pct_change(1)
    feat["return_5d"] = feat["close"].pct_change(5)
    feat["return_10d"] = feat["close"].pct_change(10)
    feat["return_20d"] = feat["close"].pct_change(20)

    # Volatility features
    feat["volatility_5d"] = feat["return_1d"].rolling(5).std()
    feat["volatility_20d"] = feat["return_1d"].rolling(20).std()

    # Price relative to moving averages
    for p in [20, 50, 200]:
        col = f"SMA_{p}"
        if col in feat.columns:
            feat[f"price_to_sma{p}"] = feat["close"] / feat[col].replace(0, np.nan) - 1

    # High-low range
    feat["hl_range"] = (feat["high"] - feat["low"]) / feat["close"].replace(0, np.nan)

    # Volume features
    if feat["volume"].sum() > 0:
        feat["volume_sma20"] = feat["volume"].rolling(20).mean()
        feat["volume_ratio"] = feat["volume"] / feat["volume_sma20"].replace(0, np.nan)
    else:
        feat["volume_ratio"] = 1.0

    # Momentum features
    feat["roc_5"] = feat["close"].pct_change(5)
    feat["roc_10"] = feat["close"].pct_change(10)

    # Day of week (if datetime index)
    if hasattr(feat.index, "dayofweek"):
        feat["day_of_week"] = feat.index.dayofweek

    return feat


def prepare_xgboost_data(df: pd.DataFrame, forward_days: int = None):
    """Prepare features and labels for XGBoost classification.

    Labels: 0=DOWN, 1=FLAT, 2=UP based on forward_days return.

    Returns:
        X (DataFrame), y (Series), feature_names (list)
    """
    if forward_days is None:
        forward_days = ML_PARAMS["forward_days"]

    feat = build_features(df)

    # Target: forward return classification
    feat["forward_return"] = feat["close"].shift(-forward_days) / feat["close"] - 1

    # Classify: UP (>1%), DOWN (<-1%), FLAT
    feat["target"] = 1  # FLAT
    feat.loc[feat["forward_return"] > 0.01, "target"] = 2   # UP
    feat.loc[feat["forward_return"] < -0.01, "target"] = 0  # DOWN

    # Select feature columns (exclude OHLCV and target)
    exclude = {"open", "high", "low", "close", "volume", "forward_return", "target"}
    feature_cols = [c for c in feat.columns if c not in exclude and feat[c].dtype in ("float64", "float32", "int64")]

    # Drop rows with NaN
    feat = feat.dropna(subset=feature_cols + ["target"])

    X = feat[feature_cols]
    y = feat["target"].astype(int)

    return X, y, feature_cols


def prepare_lstm_data(df: pd.DataFrame, window: int = None):
    """Prepare sequential data for LSTM.

    Returns:
        X (3D numpy array: samples x window x features),
        y (1D numpy array: forward returns),
        feature_names (list)
    """
    if window is None:
        window = ML_PARAMS["lstm_window"]

    feat = build_features(df)

    # Target: 5-day forward return (continuous)
    forward_days = ML_PARAMS["forward_days"]
    feat["forward_return"] = feat["close"].shift(-forward_days) / feat["close"] - 1

    # Normalize features
    exclude = {"open", "high", "low", "close", "volume", "forward_return"}
    feature_cols = [c for c in feat.columns if c not in exclude and feat[c].dtype in ("float64", "float32", "int64")]

    feat = feat.dropna(subset=feature_cols + ["forward_return"])

    # Z-score normalization using rolling window
    X_raw = feat[feature_cols].values
    y_raw = feat["forward_return"].values

    # Create sliding windows
    X_windows = []
    y_windows = []
    for i in range(window, len(X_raw)):
        window_data = X_raw[i - window:i]
        # Normalize within each window
        mean = window_data.mean(axis=0)
        std = window_data.std(axis=0) + 1e-8
        window_normalized = (window_data - mean) / std
        X_windows.append(window_normalized)
        y_windows.append(y_raw[i])

    if not X_windows:
        return np.array([]), np.array([]), feature_cols

    X = np.array(X_windows)
    y = np.array(y_windows)

    return X, y, feature_cols
