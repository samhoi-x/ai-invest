"""Adaptive BUY/SELL thresholds that tighten in fearful markets.

Instead of using static config thresholds for every market condition,
this module adjusts the bar for signalling BUY/SELL based on:
  - VIX level (market fear gauge)
  - Macro regime (RISK_OFF / CAUTIOUS / NEUTRAL / CONSTRUCTIVE / RISK_ON)
  - Market breadth regime (POOR / WEAK / NEUTRAL / HEALTHY)

High-fear environments raise the BUY threshold and minimum confidence,
reducing false positives and protecting capital during volatile periods.
Calm environments slightly lower the bar to capture opportunities.

Base thresholds (from config):
    BUY_THRESHOLD     = 0.30  BUY_CONFIDENCE_MIN  = 0.65
    SELL_THRESHOLD    = -0.20 SELL_CONFIDENCE_MIN = 0.50

Example regime adjustments (cumulative, then clamped):
    VIX > 30 + RISK_OFF macro + POOR breadth → buy_thresh up to 0.55, buy_conf up to 0.85
    VIX < 12 + RISK_ON macro + HEALTHY breadth → buy_thresh down to 0.20
"""

import numpy as np
from config import BUY_THRESHOLD, BUY_CONFIDENCE_MIN, SELL_THRESHOLD, SELL_CONFIDENCE_MIN


def get_adaptive_thresholds(
    vix_level: float | None = None,
    macro_regime: str | None = None,
    breadth_regime: str | None = None,
) -> dict:
    """Return regime-aware BUY/SELL thresholds.

    Args:
        vix_level:      Current VIX level (float), or None to skip VIX adjustment.
        macro_regime:   Macro regime string from get_macro_signal(), or None.
        breadth_regime: Breadth regime from get_market_breadth(), or None.

    Returns:
        dict with:
            buy_threshold   float   Composite score must exceed this to signal BUY
            buy_conf_min    float   Confidence must be >= this to signal BUY
            sell_threshold  float   Composite score must be below this to signal SELL
            sell_conf_min   float   Confidence must be >= this to signal SELL
            adjustments     list    Human-readable list of applied adjustments
    """
    buy_thresh  = float(BUY_THRESHOLD)        # base 0.30
    buy_conf    = float(BUY_CONFIDENCE_MIN)   # base 0.65
    sell_thresh = float(SELL_THRESHOLD)       # base -0.20
    sell_conf   = float(SELL_CONFIDENCE_MIN)  # base 0.50

    adjustments: list[str] = []

    # ── VIX adjustments ──────────────────────────────────────────────────
    if vix_level is not None and vix_level > 0:
        if vix_level > 40:
            # Extreme fear — very high bar for BUY
            buy_thresh += 0.15
            buy_conf   += 0.10
            adjustments.append(f"VIX {vix_level:.0f} (extreme) +0.15 thresh / +0.10 conf")
        elif vix_level > 30:
            # High fear — elevated bar
            buy_thresh += 0.10
            buy_conf   += 0.07
            adjustments.append(f"VIX {vix_level:.0f} (high) +0.10 thresh / +0.07 conf")
        elif vix_level > 20:
            # Moderate fear — slightly elevated
            buy_thresh += 0.05
            buy_conf   += 0.03
            adjustments.append(f"VIX {vix_level:.0f} (elevated) +0.05 thresh / +0.03 conf")
        elif vix_level < 12:
            # Very calm — slightly more aggressive
            buy_thresh -= 0.05
            buy_conf   -= 0.03
            adjustments.append(f"VIX {vix_level:.0f} (very calm) -0.05 thresh / -0.03 conf")

    # ── Macro regime adjustments ─────────────────────────────────────────
    if macro_regime == "RISK_OFF":
        buy_thresh += 0.08
        buy_conf   += 0.05
        adjustments.append("macro RISK_OFF +0.08 thresh / +0.05 conf")
    elif macro_regime == "CAUTIOUS":
        buy_thresh += 0.04
        buy_conf   += 0.02
        adjustments.append("macro CAUTIOUS +0.04 thresh / +0.02 conf")
    elif macro_regime == "RISK_ON":
        buy_thresh -= 0.03
        adjustments.append("macro RISK_ON -0.03 thresh")
    elif macro_regime == "CONSTRUCTIVE":
        buy_thresh -= 0.01
        adjustments.append("macro CONSTRUCTIVE -0.01 thresh")

    # ── Market breadth adjustments ───────────────────────────────────────
    if breadth_regime == "POOR":
        buy_thresh += 0.06
        buy_conf   += 0.04
        adjustments.append("breadth POOR +0.06 thresh / +0.04 conf")
    elif breadth_regime == "WEAK":
        buy_thresh += 0.03
        buy_conf   += 0.02
        adjustments.append("breadth WEAK +0.03 thresh / +0.02 conf")
    elif breadth_regime == "HEALTHY":
        buy_thresh -= 0.02
        adjustments.append("breadth HEALTHY -0.02 thresh")

    # ── Clamp to safe ranges ─────────────────────────────────────────────
    buy_thresh  = float(np.clip(buy_thresh,   0.15, 0.55))
    buy_conf    = float(np.clip(buy_conf,     0.50, 0.85))
    sell_thresh = float(np.clip(sell_thresh, -0.50, -0.10))
    sell_conf   = float(np.clip(sell_conf,   0.40, 0.75))

    return {
        "buy_threshold":  round(buy_thresh,  4),
        "buy_conf_min":   round(buy_conf,    4),
        "sell_threshold": round(sell_thresh, 4),
        "sell_conf_min":  round(sell_conf,   4),
        "vix_level":      vix_level,
        "macro_regime":   macro_regime,
        "breadth_regime": breadth_regime,
        "adjustments":    adjustments,
    }
