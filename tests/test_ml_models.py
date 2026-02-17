"""Tests for ML models module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from analysis.feature_engine import build_features, prepare_xgboost_data, prepare_lstm_data
from analysis.ml_models import XGBoostPredictor, LSTMPredictor, _model_is_stale


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.3,
        "high": close + abs(np.random.randn(n) * 0.5),
        "low": close - abs(np.random.randn(n) * 0.5),
        "close": close,
        "volume": np.random.randint(1000000, 10000000, n).astype(float),
    }, index=dates)


def test_build_features(sample_df):
    feat = build_features(sample_df)
    assert "RSI" in feat.columns
    assert "return_1d" in feat.columns
    assert "volatility_5d" in feat.columns
    assert len(feat) == len(sample_df)


def test_prepare_xgboost_data(sample_df):
    X, y, feature_names = prepare_xgboost_data(sample_df)
    assert len(X) > 0
    assert len(y) == len(X)
    assert len(feature_names) > 5
    assert set(y.unique()).issubset({0, 1, 2})


def test_prepare_lstm_data(sample_df):
    X, y, feature_names = prepare_lstm_data(sample_df, window=30)
    assert len(X) > 0
    assert X.shape[1] == 30  # Window size
    assert X.shape[2] == len(feature_names)


def test_xgboost_train_predict(sample_df):
    xgb = XGBoostPredictor()
    metrics = xgb.train(sample_df)
    assert "cv_accuracy" in metrics
    assert metrics["cv_accuracy"] > 0

    pred = xgb.predict(sample_df)
    assert "direction" in pred
    assert pred["direction"] in ("UP", "DOWN", "FLAT")
    assert -1 <= pred["signal_score"] <= 1


def test_xgboost_insufficient_data():
    small_df = pd.DataFrame({
        "open": [100, 101], "high": [102, 103],
        "low": [98, 99], "close": [101, 102],
        "volume": [1000, 1000],
    }, index=pd.date_range("2023-01-01", periods=2))

    xgb = XGBoostPredictor()
    result = xgb.train(small_df)
    assert "error" in result


def test_xgboost_predict_not_trained():
    xgb = XGBoostPredictor()
    result = xgb.predict(pd.DataFrame())
    assert "error" in result


def test_xgboost_feature_alignment(sample_df):
    """Test that prediction works even if features differ slightly."""
    xgb = XGBoostPredictor()
    xgb.train(sample_df)
    # Predict with same data should align features properly
    pred = xgb.predict(sample_df)
    assert "direction" in pred
    assert pred["direction"] in ("UP", "DOWN", "FLAT")


def test_lstm_train_predict(sample_df):
    lstm = LSTMPredictor()
    metrics = lstm.train(sample_df, epochs=5)
    assert "val_loss" in metrics
    assert "direction_accuracy" in metrics
    assert metrics["val_loss"] > 0

    pred = lstm.predict(sample_df)
    assert "signal_score" in pred
    assert "trend" in pred
    assert pred["trend"] in ("UP", "DOWN", "FLAT")
    assert -1 <= pred["signal_score"] <= 1


def test_lstm_predict_not_trained():
    lstm = LSTMPredictor()
    result = lstm.predict(pd.DataFrame())
    assert "error" in result


def test_lstm_insufficient_data():
    small_df = pd.DataFrame({
        "open": [100, 101], "high": [102, 103],
        "low": [98, 99], "close": [101, 102],
        "volume": [1000, 1000],
    }, index=pd.date_range("2023-01-01", periods=2))
    lstm = LSTMPredictor()
    result = lstm.train(small_df)
    assert "error" in result


def test_model_is_stale():
    from datetime import datetime, timedelta
    assert _model_is_stale(None) is True
    assert _model_is_stale("") is True
    # Model trained today should not be stale
    assert _model_is_stale(datetime.now().isoformat()) is False
    # Model trained 100 days ago should be stale (threshold is 60 days)
    old = (datetime.now() - timedelta(days=100)).isoformat()
    assert _model_is_stale(old) is True
