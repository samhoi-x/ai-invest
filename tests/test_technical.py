"""Tests for technical analysis module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from analysis.technical import (
    sma, ema, rsi, macd, bollinger_bands, atr, stochastic, obv,
    compute_all_indicators, compute_technical_signal,
    score_rsi, score_macd, score_bollinger, score_ma_trend, score_stochastic,
)


@pytest.fixture
def sample_df():
    """Create sample OHLCV data."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.3,
        "high": close + abs(np.random.randn(n) * 0.5),
        "low": close - abs(np.random.randn(n) * 0.5),
        "close": close,
        "volume": np.random.randint(1000000, 10000000, n).astype(float),
    }, index=dates)


def test_sma(sample_df):
    result = sma(sample_df["close"], 20)
    assert len(result) == len(sample_df)
    assert result.iloc[:19].isna().all()
    assert not result.iloc[19:].isna().any()


def test_ema(sample_df):
    result = ema(sample_df["close"], 12)
    assert len(result) == len(sample_df)
    assert not result.iloc[11:].isna().any()


def test_rsi(sample_df):
    result = rsi(sample_df["close"], 14)
    assert len(result) == len(sample_df)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_macd(sample_df):
    macd_line, signal_line, hist = macd(sample_df["close"])
    assert len(macd_line) == len(sample_df)
    assert len(signal_line) == len(sample_df)
    assert len(hist) == len(sample_df)


def test_bollinger_bands(sample_df):
    upper, middle, lower = bollinger_bands(sample_df["close"])
    valid_idx = ~upper.isna()
    assert (upper[valid_idx] >= middle[valid_idx]).all()
    assert (middle[valid_idx] >= lower[valid_idx]).all()


def test_atr(sample_df):
    result = atr(sample_df)
    valid = result.dropna()
    assert (valid > 0).all()


def test_stochastic(sample_df):
    k, d = stochastic(sample_df)
    valid_k = k.dropna()
    assert (valid_k >= 0).all() and (valid_k <= 100).all()


def test_obv(sample_df):
    result = obv(sample_df)
    assert len(result) == len(sample_df)


def test_compute_all_indicators(sample_df):
    result = compute_all_indicators(sample_df)
    assert "RSI" in result.columns
    assert "MACD" in result.columns
    assert "BB_upper" in result.columns
    assert "SMA_20" in result.columns
    assert "ATR" in result.columns


def test_compute_technical_signal(sample_df):
    signal = compute_technical_signal(sample_df)
    assert "score" in signal
    assert "confidence" in signal
    assert -1 <= signal["score"] <= 1
    assert 0 <= signal["confidence"] <= 1


def test_score_rsi():
    assert score_rsi(25) > 0.3  # Oversold → bullish
    assert score_rsi(75) < -0.3  # Overbought → bearish
    assert abs(score_rsi(50)) < 0.2  # Neutral


def test_score_macd():
    assert score_macd(1.0, 0.5, 0.5) > 0  # Bullish crossover
    assert score_macd(-1.0, -0.5, -0.5) < 0  # Bearish crossover


def test_score_bollinger():
    assert score_bollinger(100, 110, 90, 0.05) > 0  # Near lower band
    assert score_bollinger(100, 110, 90, 0.95) < 0  # Near upper band


def test_score_ma_trend():
    assert score_ma_trend(110, 100, 90, 80) > 0  # Price above all MAs
    assert score_ma_trend(70, 100, 90, 80) < 0  # Price below all MAs


def test_score_stochastic():
    assert score_stochastic(15, 15) > 0  # Oversold
    assert score_stochastic(85, 85) < 0  # Overbought
