"""Earnings event detection and signal confidence adjustment.

Trading into earnings is a high-uncertainty binary event — signals become
unreliable as IV expands and price gaps can invalidate any technical setup.
This module detects upcoming earnings and returns a confidence multiplier
that the signal combiner applies to the final output.

Confidence schedule
-------------------
Days to earnings    Multiplier    Effect
today (0)           0.30          Direction forced to HOLD
1–3 days            0.50          Confidence halved
4–7 days            0.75          Confidence reduced 25%
8–14 days           0.90          Minor caution
> 14 days           1.00          No adjustment

Public API
----------
get_earnings_filter(symbol) -> dict
"""

import logging
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Per-symbol result cache (12-hour TTL — earnings dates don't move intraday)
_cache: dict = {}   # {symbol: (result_dict, expires_at)}
_CACHE_TTL = 12 * 3600  # seconds


def _no_filter() -> dict:
    return {
        "confidence_multiplier": 1.0,
        "days_to_earnings": None,
        "earnings_date": None,
        "warning": None,
        "is_earnings_today": False,
    }


def _parse_earnings_date(calendar) -> Optional[pd.Timestamp]:
    """Extract the nearest upcoming earnings date from a yfinance calendar object."""
    if calendar is None:
        return None

    # yfinance ≥ 0.2.x returns a dict; older versions return a DataFrame
    if isinstance(calendar, dict):
        raw = calendar.get("Earnings Date") or calendar.get("earningsDate")
        if not raw:
            return None
        if isinstance(raw, (list, tuple)) and len(raw) > 0:
            return pd.Timestamp(raw[0])
        return pd.Timestamp(raw)

    # DataFrame format (older yfinance)
    if hasattr(calendar, "columns") and not calendar.empty:
        if "Earnings Date" in calendar.columns:
            return pd.Timestamp(calendar["Earnings Date"].iloc[0])
        # Some versions put the date in the first cell
        try:
            return pd.Timestamp(calendar.iloc[0, 0])
        except Exception:
            pass

    return None


def _fetch_earnings_filter(symbol: str) -> dict:
    """Fetch earnings calendar and compute confidence adjustment."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        earnings_date = _parse_earnings_date(calendar)

        if earnings_date is None:
            return _no_filter()

        today = pd.Timestamp.now().normalize()
        earnings_date = earnings_date.normalize()
        days_diff = (earnings_date - today).days

        # Only care about earnings coming up within 14 days
        if days_diff < 0 or days_diff > 14:
            return _no_filter()

        date_str = earnings_date.strftime("%Y-%m-%d")

        if days_diff == 0:
            return {
                "confidence_multiplier": 0.30,
                "days_to_earnings": 0,
                "earnings_date": date_str,
                "warning": (f"EARNINGS TODAY ({date_str}) — "
                            "Signal unreliable; HOLD recommended"),
                "is_earnings_today": True,
            }
        elif days_diff <= 3:
            return {
                "confidence_multiplier": 0.50,
                "days_to_earnings": days_diff,
                "earnings_date": date_str,
                "warning": (f"Earnings in {days_diff} day(s) ({date_str}) — "
                            "Confidence reduced 50%"),
                "is_earnings_today": False,
            }
        elif days_diff <= 7:
            return {
                "confidence_multiplier": 0.75,
                "days_to_earnings": days_diff,
                "earnings_date": date_str,
                "warning": (f"Earnings in {days_diff} day(s) ({date_str}) — "
                            "Confidence reduced 25%"),
                "is_earnings_today": False,
            }
        else:
            return {
                "confidence_multiplier": 0.90,
                "days_to_earnings": days_diff,
                "earnings_date": date_str,
                "warning": (f"Earnings in {days_diff} day(s) ({date_str}) — "
                            "Minor caution"),
                "is_earnings_today": False,
            }

    except Exception as exc:
        logger.warning("Earnings filter failed for %s: %s", symbol, exc)
        return _no_filter()


def get_earnings_filter(symbol: str) -> dict:
    """Return confidence multiplier based on upcoming earnings proximity.

    Crypto symbols (containing '/') always return the no-op filter.
    Results are cached per symbol for 12 hours.

    Parameters
    ----------
    symbol : ticker string (e.g. 'AAPL' or 'BTC/USDT')

    Returns
    -------
    dict with keys:
        confidence_multiplier  float   1.0 = unchanged, 0.3 = earnings today
        days_to_earnings       int | None
        earnings_date          str | None   'YYYY-MM-DD'
        warning                str | None   human-readable message
        is_earnings_today      bool
    """
    # Crypto has no earnings
    if "/" in symbol:
        return _no_filter()

    now = time.monotonic()
    if symbol in _cache:
        result, expires_at = _cache[symbol]
        if now < expires_at:
            return result

    result = _fetch_earnings_filter(symbol)
    _cache[symbol] = (result, now + _CACHE_TTL)

    if result["warning"]:
        logger.info("Earnings filter %s: %s", symbol, result["warning"])

    return result
