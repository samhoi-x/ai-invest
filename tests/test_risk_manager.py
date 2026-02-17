"""Tests for risk manager module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from strategy.risk_manager import (
    check_position_limits, calculate_stop_loss, check_drawdown,
    check_cash_reserve, filter_signal_by_risk,
)


def test_position_limits_within():
    result = check_position_limits("AAPL", 10000, 100000, "stock")
    assert result["allowed"] is True
    assert len(result["violations"]) == 0


def test_position_limits_exceeded():
    result = check_position_limits("AAPL", 20000, 100000, "stock")
    assert result["allowed"] is False
    assert len(result["violations"]) > 0


def test_stop_loss_with_atr():
    stops = calculate_stop_loss(entry_price=100, atr_value=2.0)
    assert stops["atr_stop"] == 96.0  # 100 - 2*2
    assert stops["pct_stop"] == 95.0  # 100 * 0.95
    assert stops["trailing_stop"] == 93.0  # 100 * 0.93
    assert stops["recommended"] == 96.0  # Tightest (highest) stop


def test_stop_loss_without_atr():
    stops = calculate_stop_loss(entry_price=100)
    assert stops["atr_stop"] is None
    assert stops["pct_stop"] == 95.0
    assert stops["recommended"] == 95.0


def test_drawdown_ok():
    equity = [100000, 102000, 101000, 103000]
    result = check_drawdown(equity)
    assert result["status"] == "OK"
    assert len(result["actions"]) == 0


def test_drawdown_warning():
    equity = [100000, 100000, 93000]  # ~7% drawdown
    result = check_drawdown(equity)
    # 7% is below 8% warning threshold
    assert result["status"] == "OK"


def test_drawdown_halt():
    equity = [100000, 100000, 87000]  # 13% drawdown
    result = check_drawdown(equity)
    assert result["status"] == "HALT"
    assert any("Stop" in a for a in result["actions"])


def test_drawdown_critical():
    equity = [100000, 100000, 84000]  # 16% drawdown
    result = check_drawdown(equity)
    assert result["status"] == "CRITICAL"


def test_cash_reserve_ok():
    result = check_cash_reserve(15000, 100000)
    assert result["ok"] is True


def test_cash_reserve_low():
    result = check_cash_reserve(5000, 100000)
    assert result["ok"] is False


def test_filter_signal_buy_during_halt():
    signal = {"direction": "BUY", "strength": 0.5, "confidence": 0.8}
    equity = [100000, 100000, 87000]  # Drawdown halt
    result = filter_signal_by_risk(signal, 87000, 10000, equity)
    assert result["direction"] == "HOLD"
    assert "risk_override" in result


def test_filter_signal_buy_low_cash():
    signal = {"direction": "BUY", "strength": 0.5, "confidence": 0.8}
    equity = [100000, 100000, 99000]  # OK drawdown
    result = filter_signal_by_risk(signal, 100000, 5000, equity)
    assert result["direction"] == "HOLD"  # Blocked by cash reserve


def test_filter_signal_sell_passes():
    signal = {"direction": "SELL", "strength": -0.5, "confidence": 0.8}
    equity = [100000, 100000, 87000]  # Even during halt, SELL passes
    result = filter_signal_by_risk(signal, 87000, 10000, equity)
    assert result["direction"] == "SELL"


def test_empty_equity_curve():
    result = check_drawdown([])
    assert result["status"] == "OK"
    assert result["current_drawdown"] == 0
