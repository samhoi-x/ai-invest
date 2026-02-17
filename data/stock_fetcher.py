"""Stock data fetcher using yfinance with retry and cache fallback."""

import yfinance as yf
import pandas as pd
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5  # seconds


def _retry(func, *args, retries=_MAX_RETRIES, **kwargs):
    """Call func with exponential backoff retries."""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == retries - 1:
                logger.warning("Failed after %d retries: %s", retries, e)
                raise
            wait = _BACKOFF_BASE ** attempt
            logger.info("Retry %d/%d after %.1fs: %s", attempt + 1, retries, wait, e)
            time.sleep(wait)


def fetch_stock_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch historical stock data with retry logic.

    Args:
        symbol: Stock ticker (e.g., 'AAPL')
        period: Data period ('1mo', '3mo', '6mo', '1y', '2y', '5y')
        interval: Data interval ('1d', '1wk', '1mo')

    Returns:
        DataFrame with OHLCV data.
    """
    try:
        ticker = _retry(lambda: yf.Ticker(symbol))
        df = _retry(lambda: ticker.history(period=period, interval=interval))
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]]
    return df


def fetch_stock_info(symbol: str) -> dict:
    """Fetch stock metadata (sector, name, market cap, etc.)."""
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    return {
        "symbol": symbol,
        "name": info.get("shortName", symbol),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": info.get("marketCap", 0),
        "pe_ratio": info.get("trailingPE", None),
        "dividend_yield": info.get("dividendYield", None),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", None),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", None),
    }


def fetch_multiple_stocks(symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Fetch data for multiple symbols."""
    results = {}
    for sym in symbols:
        try:
            df = fetch_stock_data(sym, period=period)
            if not df.empty:
                results[sym] = df
        except Exception:
            continue
    return results


def get_current_price(symbol: str) -> dict | None:
    """Get current price and change for a stock with retry."""
    try:
        ticker = yf.Ticker(symbol)
        hist = _retry(lambda: ticker.history(period="5d"))
        if hist.empty or len(hist) < 2:
            return None
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        change = current - prev
        change_pct = (change / prev) * 100
        return {
            "symbol": symbol,
            "price": round(current, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        return None
