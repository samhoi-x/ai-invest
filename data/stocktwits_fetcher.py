"""StockTwits real-time social sentiment fetcher.

Uses the free, unauthenticated StockTwits public API to fetch recent
message streams for a ticker symbol.  No API key required.

Endpoint:  https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json
Rate limit: ~200 req/hour unauthenticated.  The module enforces a
            15-minute per-symbol cache so normal operation stays well
            within limits even when the scheduler scans many tickers.

Sentiment data quality:
  StockTwits users tag messages as Bullish / Bearish.  We expose the
  raw message bodies so the existing FinBERT-based sentiment model can
  score them, giving us a *second* retail-sentiment source complementary
  to Reddit (which skews toward longer-form analysis).

Public API
----------
fetch_stocktwits_posts(symbol, limit=30) -> list[str]
    Returns a list of message body strings (may be empty on error).
"""

import logging
import time

logger = logging.getLogger(__name__)

_CACHE_TTL = 15 * 60  # 15-minute per-symbol cache
_cache: dict[str, dict] = {}


def fetch_stocktwits_posts(symbol: str, limit: int = 30) -> list[str]:
    """Fetch recent StockTwits messages for a symbol.

    Args:
        symbol: Ticker (e.g. "AAPL", "BTC", "BTC/USDT").
                Crypto pairs are normalised automatically (BTC/USDT → BTC).
        limit:  Maximum messages to return.  StockTwits free tier returns
                up to 30 messages per request; larger values are silently
                capped to 30.

    Returns:
        List of raw message body strings.  Returns [] on error or rate-limit.
    """
    # Normalise: strip crypto pair suffix and force uppercase
    clean = symbol.split("/")[0].upper()

    # Cache check
    now = time.monotonic()
    entry = _cache.get(clean)
    if entry is not None and now < entry["expires_at"]:
        logger.debug("StockTwits cache hit for %s (%d messages)", clean, len(entry["messages"]))
        return entry["messages"]

    messages: list[str] = []
    try:
        import requests

        url = f"https://api.stocktwits.com/api/2/streams/symbol/{clean}.json"
        resp = requests.get(url, timeout=8, params={"limit": min(limit, 30)})

        if resp.status_code == 429:
            logger.warning("StockTwits rate limit hit for %s — returning empty", clean)
            # Short cache so next call retries sooner
            _cache[clean] = {"messages": [], "expires_at": now + 60}
            return []

        if resp.status_code == 404:
            # Unknown ticker — cache indefinitely (within TTL) to avoid retries
            logger.debug("StockTwits: symbol %s not found (404)", clean)
            _cache[clean] = {"messages": [], "expires_at": now + _CACHE_TTL}
            return []

        if resp.status_code != 200:
            logger.debug("StockTwits returned HTTP %d for %s", resp.status_code, clean)
            return []

        data = resp.json()
        messages = [
            m["body"]
            for m in data.get("messages", [])
            if m.get("body") and len(m["body"].strip()) > 5
        ]

        logger.debug("StockTwits: %d messages fetched for %s", len(messages), clean)

    except Exception as exc:
        logger.debug("StockTwits fetch failed for %s: %s", clean, exc)

    _cache[clean] = {"messages": messages, "expires_at": now + _CACHE_TTL}
    return messages
