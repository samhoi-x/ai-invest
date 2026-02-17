"""News data fetcher using MarketAux and Finnhub free APIs with retry."""

import requests
import time
import logging
from datetime import datetime, timedelta
from config import MARKETAUX_API_KEY, FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_BACKOFF_BASE = 1.5


def _request_with_retry(url: str, params: dict, timeout: int = 10) -> requests.Response:
    """HTTP GET with exponential backoff retry."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = _BACKOFF_BASE ** attempt
            logger.info("News API retry %d/%d after %.1fs: %s", attempt + 1, _MAX_RETRIES, wait, e)
            time.sleep(wait)


def fetch_marketaux_news(symbol: str, limit: int = 10) -> list[dict]:
    """Fetch news from MarketAux API (free tier: 100 req/day)."""
    if not MARKETAUX_API_KEY:
        return []
    try:
        resp = _request_with_retry(
            "https://api.marketaux.com/v1/news/all",
            params={
                "symbols": symbol,
                "filter_entities": "true",
                "language": "en",
                "limit": limit,
                "api_token": MARKETAUX_API_KEY,
            },
        )
        data = resp.json()
        articles = []
        for item in data.get("data", []):
            articles.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "published_at": item.get("published_at", ""),
            })
        return articles
    except Exception:
        return []


def fetch_finnhub_news(symbol: str, days: int = 7) -> list[dict]:
    """Fetch news from Finnhub API (free tier: 60 calls/min)."""
    if not FINNHUB_API_KEY:
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        resp = _request_with_retry(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol,
                "from": start,
                "to": today,
                "token": FINNHUB_API_KEY,
            },
        )
        articles = []
        for item in resp.json()[:20]:
            articles.append({
                "title": item.get("headline", ""),
                "description": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "published_at": datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
            })
        return articles
    except Exception:
        return []


def fetch_news(symbol: str) -> list[dict]:
    """Fetch news from all available sources, deduplicate by title.

    Falls back to cached news if live fetch returns nothing.
    """
    articles = []
    articles.extend(fetch_marketaux_news(symbol))
    # Finnhub works with stock tickers (strip /USDT for crypto)
    ticker = symbol.split("/")[0]
    articles.extend(fetch_finnhub_news(ticker))

    # Deduplicate by title
    seen = set()
    unique = []
    for art in articles:
        key = art["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(art)

    # Fallback to cache if live fetch returned nothing
    if not unique:
        try:
            from data.cache_manager import get_cached_news
            cached = get_cached_news(symbol)
            if cached:
                logger.info("Using cached news for %s (live fetch returned empty)", symbol)
                return cached
        except Exception:
            pass

    # Cache successful results for future fallback
    if unique:
        try:
            from data.cache_manager import cache_news
            cache_news(symbol, unique)
        except Exception:
            pass

    return unique
