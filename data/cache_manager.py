"""SQLite cache layer for price and other data."""

import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from db.database import get_db
from config import CACHE_TTL

logger = logging.getLogger(__name__)


def _is_stale(fetched_at_str: str, ttl_minutes: int) -> bool:
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
    except (ValueError, TypeError):
        logger.warning("Could not parse cache timestamp '%s', treating as stale", fetched_at_str)
        return True
    # SQLite datetime('now') stores UTC, so compare with UTC
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    return now_utc - fetched_at > timedelta(minutes=ttl_minutes)


def cache_price_data(symbol: str, df: pd.DataFrame, asset_type: str = "stock"):
    """Store OHLCV data in the cache."""
    if df.empty:
        return
    dates = [str(idx.date()) if hasattr(idx, "date") else str(idx) for idx in df.index]
    volume = df["volume"].tolist() if "volume" in df.columns else [0] * len(df)
    rows = list(zip(
        [symbol] * len(df), dates,
        df["open"].tolist(), df["high"].tolist(), df["low"].tolist(), df["close"].tolist(),
        volume, [asset_type] * len(df),
    ))
    with get_db() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO price_cache
            (symbol, date, open, high, low, close, volume, asset_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def get_cached_price_data(symbol: str, asset_type: str = "stock",
                          days: int = 365) -> pd.DataFrame | None:
    """Retrieve cached price data if fresh enough."""
    with get_db() as conn:
        # Check freshness of the latest entry
        row = conn.execute("""
            SELECT fetched_at FROM price_cache
            WHERE symbol=? AND asset_type=?
            ORDER BY date DESC LIMIT 1
        """, (symbol, asset_type)).fetchone()

        if not row or _is_stale(row["fetched_at"], CACHE_TTL["price_minutes"]):
            return None

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume FROM price_cache
            WHERE symbol=? AND asset_type=? AND date >= ?
            ORDER BY date
        """, (symbol, asset_type, cutoff)).fetchall()

        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df


def cache_news(symbol: str, articles: list[dict]):
    """Store news articles in cache."""
    with get_db() as conn:
        for art in articles:
            conn.execute("""
                INSERT INTO news_cache (symbol, title, description, source, url, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol, art.get("title", ""), art.get("description", ""),
                  art.get("source", ""), art.get("url", ""),
                  art.get("published_at", "")))


def get_cached_news(symbol: str, limit: int = 20) -> list[dict] | None:
    """Retrieve cached news if fresh."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT fetched_at FROM news_cache
            WHERE symbol=?
            ORDER BY fetched_at DESC LIMIT 1
        """, (symbol,)).fetchone()

        if not row or _is_stale(row["fetched_at"], CACHE_TTL["news_minutes"]):
            return None

        rows = conn.execute("""
            SELECT title, description, source, url, published_at
            FROM news_cache WHERE symbol=?
            ORDER BY published_at DESC LIMIT ?
        """, (symbol, limit)).fetchall()
        return [dict(r) for r in rows] if rows else None


def cache_sentiment(symbol: str, source: str, score: float, label: str, snippet: str = ""):
    """Store a sentiment score."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO sentiment_scores (symbol, source, score, label, text_snippet)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, source, score, label, snippet))


def get_cached_sentiment(symbol: str) -> list[dict] | None:
    """Retrieve cached sentiment scores if fresh."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT computed_at FROM sentiment_scores
            WHERE symbol=?
            ORDER BY computed_at DESC LIMIT 1
        """, (symbol,)).fetchone()

        if not row or _is_stale(row["computed_at"], CACHE_TTL["sentiment_minutes"]):
            return None

        rows = conn.execute("""
            SELECT source, score, label, text_snippet, computed_at
            FROM sentiment_scores WHERE symbol=?
            ORDER BY computed_at DESC LIMIT 50
        """, (symbol,)).fetchall()
        return [dict(r) for r in rows] if rows else None


def clear_cache(cache_type: str = "all"):
    """Clear cached data."""
    with get_db() as conn:
        if cache_type in ("price", "all"):
            conn.execute("DELETE FROM price_cache")
        if cache_type in ("news", "all"):
            conn.execute("DELETE FROM news_cache")
        if cache_type in ("sentiment", "all"):
            conn.execute("DELETE FROM sentiment_scores")
        if cache_type in ("predictions", "all"):
            conn.execute("DELETE FROM ml_predictions")
