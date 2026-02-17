"""Tests for signal combiner module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from strategy.signal_combiner import combine_signals, batch_combine


def test_combine_strong_buy():
    """All factors strongly bullish → BUY."""
    tech = {"score": 0.8, "confidence": 0.9}
    sent = {"score": 0.6, "confidence": 0.8}
    ml = {"score": 0.7, "confidence": 0.85}

    result = combine_signals(tech, sent, ml)
    assert result["direction"] == "BUY"
    assert result["strength"] > 0.3
    assert result["confidence"] > 0.5


def test_combine_strong_sell():
    """All factors strongly bearish → SELL."""
    tech = {"score": -0.7, "confidence": 0.85}
    sent = {"score": -0.5, "confidence": 0.7}
    ml = {"score": -0.6, "confidence": 0.8}

    result = combine_signals(tech, sent, ml)
    assert result["direction"] == "SELL"
    assert result["strength"] < -0.2


def test_combine_mixed_signals_hold():
    """Conflicting factors → HOLD with lower confidence."""
    tech = {"score": 0.5, "confidence": 0.7}
    sent = {"score": -0.4, "confidence": 0.6}
    ml = {"score": 0.1, "confidence": 0.5}

    result = combine_signals(tech, sent, ml)
    # With mixed signals, confidence should be penalized
    assert result["confidence"] < 0.8


def test_combine_neutral():
    """All neutral → HOLD."""
    tech = {"score": 0.05, "confidence": 0.5}
    sent = {"score": -0.05, "confidence": 0.4}
    ml = {"score": 0.0, "confidence": 0.4}

    result = combine_signals(tech, sent, ml)
    assert result["direction"] == "HOLD"


def test_combine_empty_inputs():
    """Empty inputs → HOLD."""
    result = combine_signals({}, {}, {})
    assert result["direction"] == "HOLD"
    assert result["strength"] == 0.0


def test_conservative_bias():
    """BUY requires higher threshold than SELL (capital protection)."""
    # Moderate bullish signal - should NOT trigger BUY (threshold 0.3)
    tech = {"score": 0.3, "confidence": 0.6}
    sent = {"score": 0.2, "confidence": 0.5}
    ml = {"score": 0.25, "confidence": 0.5}

    result = combine_signals(tech, sent, ml)
    # Composite ≈ 0.35*0.3 + 0.25*0.2 + 0.40*0.25 = 0.255, below 0.3 threshold
    assert result["direction"] == "HOLD"


def test_batch_combine():
    signals = {
        "AAPL": {
            "technical": {"score": 0.8, "confidence": 0.9},
            "sentiment": {"score": 0.6, "confidence": 0.8},
            "ml": {"score": 0.7, "confidence": 0.85},
        },
        "MSFT": {
            "technical": {"score": -0.5, "confidence": 0.7},
            "sentiment": {"score": -0.3, "confidence": 0.6},
            "ml": {"score": -0.4, "confidence": 0.7},
        },
    }
    results = batch_combine(signals)
    assert len(results) == 2
    assert results[0]["symbol"] == "AAPL"  # BUY should come first


def test_risk_level_assignment():
    high_conf = combine_signals(
        {"score": 0.8, "confidence": 0.95},
        {"score": 0.7, "confidence": 0.9},
        {"score": 0.9, "confidence": 0.95},
    )
    assert high_conf["risk_level"] == "LOW"
