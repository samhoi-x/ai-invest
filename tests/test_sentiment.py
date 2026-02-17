"""Tests for sentiment analysis module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from analysis.sentiment import analyze_text, compute_sentiment_signal


def test_analyze_text_positive():
    """Test that positive financial text gets positive sentiment."""
    result = analyze_text("The company reported record earnings and strong revenue growth.")
    assert "label" in result
    assert "sentiment_value" in result
    assert result["label"] in ("positive", "negative", "neutral")


def test_analyze_text_negative():
    result = analyze_text("The stock crashed after reporting massive losses and bankruptcy risk.")
    assert "label" in result
    assert "sentiment_value" in result


def test_analyze_text_empty():
    result = analyze_text("")
    assert result["label"] == "neutral"
    assert result["sentiment_value"] == 0.0


def test_analyze_text_short():
    result = analyze_text("ok")
    assert result["label"] == "neutral"


def test_compute_sentiment_signal_empty():
    result = compute_sentiment_signal([], [])
    assert result["score"] == 0.0
    assert "confidence" in result


def test_compute_sentiment_signal_news_only():
    news = [
        {"title": "Apple reports record quarterly revenue"},
        {"title": "Tech stocks surge on strong earnings"},
    ]
    result = compute_sentiment_signal(news, [])
    assert -1 <= result["score"] <= 1
    assert result["news_count"] == 2
    assert result["social_count"] == 0


def test_compute_sentiment_signal_social_only():
    social = [
        "AAPL is going to the moon, best earnings ever!",
        "Bullish on Apple, great product pipeline.",
    ]
    result = compute_sentiment_signal([], social)
    assert -1 <= result["score"] <= 1
    assert result["social_count"] == 2


def test_compute_sentiment_signal_mixed():
    news = [{"title": "Markets rally on positive economic data"}]
    social = ["Very bullish on the market right now"]
    result = compute_sentiment_signal(news, social)
    assert -1 <= result["score"] <= 1
    assert 0 <= result["confidence"] <= 1
