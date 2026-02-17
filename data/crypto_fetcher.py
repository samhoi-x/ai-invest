"""Cryptocurrency data fetcher using ccxt with exchange fallback and retry."""

import ccxt
import pandas as pd
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0

# Exchanges to try in order (Binance often blocked by region)
_EXCHANGE_CLASSES = [
    ("okx", lambda: ccxt.okx({"enableRateLimit": True})),
    ("bybit", lambda: ccxt.bybit({"enableRateLimit": True})),
    ("kucoin", lambda: ccxt.kucoin({"enableRateLimit": True})),
    ("binance", lambda: ccxt.binance({"enableRateLimit": True})),
]

_active_exchange = None
_active_name = None


def _get_exchange():
    """Get a working exchange, with fallback across multiple providers."""
    global _active_exchange, _active_name
    if _active_exchange is not None:
        return _active_exchange

    for name, factory in _EXCHANGE_CLASSES:
        try:
            ex = factory()
            ex.fetch_ticker("BTC/USDT")
            _active_exchange = ex
            _active_name = name
            logger.info("Using crypto exchange: %s", name)
            return ex
        except Exception as e:
            logger.info("Exchange %s unavailable: %s", name, e)
            continue

    # All failed — return first as default, will error on use
    logger.warning("No crypto exchange available")
    _active_exchange = _EXCHANGE_CLASSES[0][1]()
    _active_name = _EXCHANGE_CLASSES[0][0]
    return _active_exchange


def _retry(func, retries=_MAX_RETRIES):
    """Call func with exponential backoff retries."""
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            if attempt == retries - 1:
                logger.warning("Failed after %d retries: %s", retries, e)
                raise
            wait = _BACKOFF_BASE ** attempt
            logger.info("Retry %d/%d after %.1fs: %s", attempt + 1, retries, wait, e)
            time.sleep(wait)


def fetch_crypto_data(symbol: str = "BTC/USDT", timeframe: str = "1d",
                      days: int = 365) -> pd.DataFrame:
    """Fetch historical OHLCV data for a crypto pair.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframe: Candle timeframe ('1h', '4h', '1d')
        days: Number of days of history

    Returns:
        DataFrame with OHLCV data.
    """
    exchange = _get_exchange()
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())

    all_candles = []
    try:
        while True:
            candles = _retry(lambda: exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000))
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            if len(candles) < 1000:
                break
    except Exception as e:
        logger.warning("Failed to fetch crypto data for %s: %s", symbol, e)

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    df = df[~df.index.duplicated(keep="last")]
    return df


def fetch_multiple_crypto(pairs: list[str], timeframe: str = "1d",
                          days: int = 365) -> dict[str, pd.DataFrame]:
    """Fetch data for multiple crypto pairs."""
    results = {}
    for pair in pairs:
        try:
            df = fetch_crypto_data(pair, timeframe=timeframe, days=days)
            if not df.empty:
                results[pair] = df
        except Exception:
            continue
    return results


def get_crypto_price(symbol: str = "BTC/USDT") -> dict | None:
    """Get current crypto price and 24h change."""
    try:
        exchange = _get_exchange()
        ticker = _retry(lambda: exchange.fetch_ticker(symbol))
        return {
            "symbol": symbol,
            "price": round(ticker["last"], 2),
            "change": round(ticker["change"] or 0, 2),
            "change_pct": round(ticker["percentage"] or 0, 2),
            "volume_24h": ticker.get("quoteVolume", 0),
            "high_24h": ticker.get("high", 0),
            "low_24h": ticker.get("low", 0),
        }
    except Exception:
        return None


def get_multiple_crypto_prices(pairs: list[str]) -> list[dict]:
    """Get current prices for multiple crypto pairs."""
    results = []
    for pair in pairs:
        price = get_crypto_price(pair)
        if price:
            results.append(price)
    return results
