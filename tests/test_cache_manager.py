"""Tests for cache manager module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime


@pytest.fixture(autouse=True)
def init_db():
    """Ensure database exists before tests."""
    from db.database import init_db
    init_db()


@pytest.fixture
def sample_df():
    # Use recent dates so cache freshness and date-range filter work
    dates = pd.date_range(datetime.now() - pd.Timedelta(days=20), periods=10, freq="B")
    return pd.DataFrame({
        "open": np.random.uniform(100, 110, 10),
        "high": np.random.uniform(110, 115, 10),
        "low": np.random.uniform(95, 100, 10),
        "close": np.random.uniform(100, 110, 10),
        "volume": np.random.randint(1000, 10000, 10).astype(float),
    }, index=dates)


def test_cache_and_retrieve_price(sample_df):
    from data.cache_manager import cache_price_data, get_cached_price_data
    cache_price_data("TEST_SYM", sample_df, "stock")
    cached = get_cached_price_data("TEST_SYM", "stock")
    assert cached is not None
    assert len(cached) == len(sample_df)
    assert "close" in cached.columns


def test_cache_returns_none_for_unknown():
    from data.cache_manager import get_cached_price_data
    cached = get_cached_price_data("NONEXISTENT_XYZ", "stock")
    assert cached is None


def test_cache_news():
    from data.cache_manager import cache_news, get_cached_news
    articles = [
        {"title": "Test headline 1", "description": "Desc", "source": "Test", "url": "", "published_at": "2023-01-01"},
        {"title": "Test headline 2", "description": "Desc", "source": "Test", "url": "", "published_at": "2023-01-02"},
    ]
    cache_news("TEST_NEWS", articles)
    cached = get_cached_news("TEST_NEWS")
    assert cached is not None
    assert len(cached) >= 2


def test_clear_cache():
    from data.cache_manager import cache_price_data, clear_cache, get_cached_price_data
    dates = pd.date_range("2023-06-01", periods=5, freq="B")
    df = pd.DataFrame({
        "open": [100]*5, "high": [105]*5, "low": [95]*5,
        "close": [102]*5, "volume": [1000]*5,
    }, index=dates)
    cache_price_data("CLEAR_TEST", df, "stock")
    clear_cache("price")
    cached = get_cached_price_data("CLEAR_TEST", "stock")
    assert cached is None


def test_clear_all_cache():
    from data.cache_manager import clear_cache
    clear_cache("all")  # Should not raise
