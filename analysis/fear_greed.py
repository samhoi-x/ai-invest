"""Fear & Greed Index — contrarian sentiment signal.

Two data sources (4-hour cached):
  alternative.me   Crypto Fear & Greed Index    (free JSON, no auth)
  CNN              Stock Market Fear & Greed     (public production API)

Contrarian scoring logic (score mapped to -1 to +1):
  0-25   Extreme Fear  → +0.40 to +0.80  (classic buy-the-fear)
  25-45  Fear          → +0.20 to +0.40
  45-55  Neutral       →  0.00
  55-75  Greed         → -0.05 to -0.15  (caution)
  75-100 Extreme Greed → -0.15 to -0.30  (contrarian sell signal)

Rationale: Extreme fear → most sellers have already sold → mean-reversion
           Extreme greed → complacency risk → mean-reversion downward

Public API
----------
get_fear_greed_signal(asset_type="stock") -> dict
    4-hour cached, never raises.
    Returns: {score, fg_index, fg_label, confidence, source}
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 4 * 3600  # 4-hour cache
_cache: dict = {
    "stock": None,  "stock_exp": 0.0,
    "crypto": None, "crypto_exp": 0.0,
}

_NEUTRAL = {
    "score": 0.0,
    "fg_index": 50.0,
    "fg_label": "Neutral",
    "confidence": 0.0,
    "source": None,
}


# ── Scoring ────────────────────────────────────────────────────────────────────

def _fg_label(value: float) -> str:
    if value <= 25:
        return "Extreme Fear"
    elif value <= 45:
        return "Fear"
    elif value <= 55:
        return "Neutral"
    elif value <= 75:
        return "Greed"
    else:
        return "Extreme Greed"


def _score_fg(fg_value: float) -> float:
    """Map Fear & Greed 0-100 to contrarian signal in [-1, +1]."""
    if fg_value <= 25:
        # Extreme Fear: 25→+0.40, 0→+0.80 (linear)
        return 0.40 + (25 - fg_value) / 25 * 0.40
    elif fg_value <= 45:
        # Fear: 45→+0.20, 25→+0.40 (linear)
        return 0.20 + (45 - fg_value) / 20 * 0.20
    elif fg_value <= 55:
        # Neutral: 0
        return 0.0
    elif fg_value <= 75:
        # Greed: 55→0, 75→-0.15 (linear)
        return -0.15 * (fg_value - 55) / 20
    else:
        # Extreme Greed: 75→-0.15, 100→-0.30 (linear)
        return -0.15 + (fg_value - 75) / 25 * (-0.15)


# ── Data fetchers ──────────────────────────────────────────────────────────────

def _fetch_crypto_fg() -> Optional[tuple[float, str]]:
    """Fetch Crypto Fear & Greed from alternative.me (free, no auth)."""
    try:
        import requests
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        entry = data["data"][0]
        value = float(entry["value"])
        label = entry.get("value_classification") or _fg_label(value)
        return value, label
    except Exception as exc:
        logger.debug("Crypto F&G fetch failed: %s", exc)
        return None


def _fetch_stock_fg() -> Optional[tuple[float, str]]:
    """Fetch Stock Market Fear & Greed from CNN production API."""
    try:
        import requests
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        fg_data = data.get("fear_and_greed", {})
        raw_score = fg_data.get("score")
        if raw_score is None:
            return None
        value = float(raw_score)
        label = fg_data.get("rating") or _fg_label(value)
        return value, label
    except Exception as exc:
        logger.debug("Stock F&G fetch failed: %s", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_fear_greed_signal(asset_type: str = "stock") -> dict:
    """Return Fear & Greed contrarian signal (4-hour cached, never raises).

    Args:
        asset_type: "stock" or "crypto"

    Returns:
        dict with:
            score       float  Contrarian signal (-1 to +1)
            fg_index    float  Raw Fear & Greed index (0-100)
            fg_label    str    "Extreme Fear" / "Fear" / "Neutral" / "Greed" / "Extreme Greed"
            confidence  float  0.80 if data available, 0.0 if fallback
            source      str    Data source name, or None
    """
    now = time.monotonic()
    ck = "crypto" if asset_type == "crypto" else "stock"
    ek = ck + "_exp"

    if _cache[ck] is not None and now < _cache[ek]:
        return _cache[ck]

    raw: Optional[tuple[float, str]] = None
    source: Optional[str] = None

    if asset_type == "crypto":
        raw = _fetch_crypto_fg()
        source = "alternative.me"
    else:
        raw = _fetch_stock_fg()
        source = "CNN"
        if raw is None:
            # Fallback: crypto F&G is correlated with risk appetite generally
            raw = _fetch_crypto_fg()
            source = "alternative.me (fallback)"

    if raw is not None:
        fg_value, fg_label_str = raw
        result: dict = {
            "score":      round(_score_fg(fg_value), 4),
            "fg_index":   round(fg_value, 1),
            "fg_label":   fg_label_str,
            "confidence": 0.80,
            "source":     source,
        }
        logger.info(
            "Fear & Greed (%s): %s %.0f (%s) → contrarian score %.3f",
            asset_type, source, fg_value, fg_label_str, result["score"],
        )
    else:
        logger.warning("Fear & Greed: all sources failed for %s, returning neutral", asset_type)
        result = dict(_NEUTRAL)

    _cache[ck] = result
    _cache[ek] = now + _CACHE_TTL
    return result
