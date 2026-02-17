"""Tests for backtester engine."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from strategy.backtester import BacktestEngine


@pytest.fixture
def price_data():
    """Create synthetic price data for 2 stocks."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2022-01-01", periods=n, freq="B")

    data = {}
    for sym in ["AAPL", "MSFT"]:
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        close = np.maximum(close, 10)  # Prevent negative prices
        data[sym] = pd.DataFrame({
            "open": close + np.random.randn(n) * 0.3,
            "high": close + abs(np.random.randn(n) * 0.5),
            "low": close - abs(np.random.randn(n) * 0.5),
            "close": close,
            "volume": np.random.randint(1000000, 10000000, n).astype(float),
        }, index=dates)
    return data


def test_backtest_runs(price_data):
    engine = BacktestEngine(initial_capital=100000, position_size_pct=0.10)
    results = engine.run(price_data)
    assert "total_return" in results
    assert "equity_curve" in results
    assert "trades" in results
    assert len(results["equity_curve"]) > 0


def test_backtest_equity_curve_length(price_data):
    engine = BacktestEngine()
    results = engine.run(price_data)
    assert len(results["equity_curve"]) == len(results["dates"])


def test_backtest_benchmark(price_data):
    engine = BacktestEngine()
    results = engine.run(price_data)
    assert "benchmark" in results
    assert len(results["benchmark"]) > 0


def test_backtest_metrics_reasonable(price_data):
    engine = BacktestEngine()
    results = engine.run(price_data)
    assert -1 <= results["total_return"] <= 10  # Reasonable range
    assert 0 <= results["max_drawdown"] <= 1
    assert 0 <= results["win_rate"] <= 1


def test_backtest_custom_signal(price_data):
    """Test with a custom always-buy signal."""
    def always_buy(df):
        return {"score": 0.9, "confidence": 0.9}

    engine = BacktestEngine(initial_capital=100000, position_size_pct=0.05)
    results = engine.run(price_data, signal_func=always_buy)
    assert results["total_trades"] > 0


def test_backtest_empty_data():
    engine = BacktestEngine()
    results = engine.run({})
    assert "error" in results


def test_backtest_single_asset():
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10)
    data = {"SPY": pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": [1000000.0] * n,
    }, index=dates)}

    engine = BacktestEngine()
    results = engine.run(data)
    assert "total_return" in results
