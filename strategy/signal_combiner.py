"""Multi-factor signal fusion engine."""

import time
import logging
import numpy as np
from config import (SIGNAL_WEIGHTS, BUY_THRESHOLD, BUY_CONFIDENCE_MIN,
                    SELL_THRESHOLD, SELL_CONFIDENCE_MIN)
from strategy.adaptive_thresholds import get_adaptive_thresholds

logger = logging.getLogger(__name__)

# ── Adaptive-weight cache ─────────────────────────────────────────────
# Refreshed at most once per hour to avoid DB hits on every signal call.
_WEIGHTS_TTL = 3600  # seconds
_weights_cache: dict = {"weights": None, "expires_at": 0.0}


def get_adaptive_weights() -> dict:
    """Return factor weights, preferring history-derived values over config defaults.

    Calls ``accuracy_tracker.compute_adaptive_weights`` at most once per hour.
    Falls back to config ``SIGNAL_WEIGHTS`` if the tracker raises any error or
    there is insufficient history.
    """
    now = time.monotonic()
    cached_w = _weights_cache["weights"]
    if cached_w is not None and now < _weights_cache["expires_at"] and "macro" in cached_w:
        return cached_w

    try:
        from analysis.accuracy_tracker import compute_adaptive_weights
        weights = compute_adaptive_weights()
    except Exception as exc:
        logger.warning("get_adaptive_weights: falling back to config defaults (%s)", exc)
        weights = dict(SIGNAL_WEIGHTS)

    _weights_cache["weights"] = weights
    _weights_cache["expires_at"] = now + _WEIGHTS_TTL
    return weights


def combine_signals(technical: dict, sentiment: dict, ml: dict,
                    macro: dict | None = None,
                    mtf: dict | None = None,
                    earnings_filter: dict | None = None,
                    breadth: dict | None = None,
                    analyst: dict | None = None,
                    intermarket: dict | None = None,
                    fear_greed: dict | None = None,
                    sector: dict | None = None,
                    short_interest: dict | None = None,
                    options: dict | None = None) -> dict:
    """Combine signal sources into a final recommendation.

    Args:
        technical:       dict with 'score' (-1 to +1) and 'confidence'
        sentiment:       dict with 'score' (-1 to +1) and 'confidence'
        ml:              dict with 'score' (-1 to +1) and 'confidence'
        macro:           dict from get_macro_signal(), or None (weight redistributed)
        mtf:             dict from compute_mtf_signal(); blends into technical component
        earnings_filter: dict from get_earnings_filter(); multiplies final confidence

    Returns:
        dict with 'direction', 'strength', 'confidence', factor breakdown,
        macro keys, mtf keys, and earnings_warning.
    """
    w = get_adaptive_weights()

    t_score = float(technical.get("score", 0))
    s_score = float(sentiment.get("score", 0))
    m_score = float(ml.get("score", 0))

    # ── Analyst consensus: blended into sentiment (30% analyst, 70% original) ─
    analyst_score: float = 0.0
    if analyst is not None and analyst.get("total_ratings", 0) > 0:
        analyst_score = float(analyst.get("score", 0.0))
        s_score = 0.70 * s_score + 0.30 * analyst_score

    # ── Fear & Greed: contrarian blend into sentiment (20% F&G, 80% original) ─
    fg_score: float = 0.0
    fg_index: float | None = None
    fg_label: str = "N/A"
    if fear_greed is not None and fear_greed.get("confidence", 0) > 0:
        fg_score = float(fear_greed.get("score", 0.0))
        fg_index = fear_greed.get("fg_index")
        fg_label = fear_greed.get("fg_label", "N/A")
        s_score = 0.80 * s_score + 0.20 * fg_score

    t_conf = float(technical.get("confidence", 0))
    s_conf = float(sentiment.get("confidence", 0))
    m_conf = float(ml.get("confidence", 0))

    # ── MTF: blend into technical component before weighting ─────────────
    mtf_alignment: float = 0.5
    if mtf is not None and mtf.get("timeframes_available"):
        mtf_score = float(mtf.get("score", 0.0))
        mtf_alignment = float(mtf.get("alignment", 0.5))
        # 70% original technical, 30% MTF consensus
        t_score = 0.70 * t_score + 0.30 * mtf_score
        # Alignment delta: perfectly aligned → +0.15 conf; conflicting → -0.15
        alignment_delta = (mtf_alignment - 0.5) * 0.30
        t_conf = float(np.clip(t_conf + alignment_delta, 0.0, 1.0))

    # ── Macro factor weights ──────────────────────────────────────────────
    macro_score_val: float = 0.0
    macro_regime: str = "UNKNOWN"
    macro_conf: float = 0.0

    if macro is not None:
        macro_score_val = float(macro.get("score", 0.0))
        macro_regime    = macro.get("regime", "UNKNOWN")
        macro_conf      = float(macro.get("confidence", 0.0))
        wt = w["technical"]
        ws = w["sentiment"]
        wm = w["ml"]
        wmacro = w["macro"]
    else:
        macro_weight = w.get("macro", 0.0)
        other_sum = w["technical"] + w["sentiment"] + w["ml"]
        scale = (other_sum + macro_weight) / other_sum if other_sum > 0 else 1.0
        wt     = w["technical"] * scale
        ws     = w["sentiment"] * scale
        wm     = w["ml"]        * scale
        wmacro = 0.0

    # ── Weighted composite score ──────────────────────────────────────────
    composite = (wt * t_score + ws * s_score + wm * m_score +
                 wmacro * macro_score_val)

    # ── Base confidence ───────────────────────────────────────────────────
    if wmacro > 0:
        base_confidence = (wt * t_conf + ws * s_conf + wm * m_conf +
                           wmacro * macro_conf)
    else:
        total_w = wt + ws + wm or 1.0
        base_confidence = (wt * t_conf + ws * s_conf + wm * m_conf) / total_w

    # ── Factor divergence penalty ─────────────────────────────────────────
    scores = [t_score, s_score, m_score]
    if macro is not None:
        scores.append(macro_score_val)
    score_std = float(np.std(scores))
    directions = [np.sign(s) if abs(s) > 0.05 else 0 for s in scores]
    disagreement_count = len(set(d for d in directions if d != 0))

    if disagreement_count >= 2:
        divergence_penalty = 0.30
    elif score_std > 0.3:
        divergence_penalty = 0.15
    else:
        divergence_penalty = 0.0

    confidence = float(np.clip(base_confidence - divergence_penalty, 0.0, 1.0))

    # ── Earnings filter: multiply confidence, override direction ──────────
    earnings_warning: str | None = None
    if earnings_filter is not None:
        mult = float(earnings_filter.get("confidence_multiplier", 1.0))
        confidence = float(np.clip(confidence * mult, 0.0, 1.0))
        earnings_warning = earnings_filter.get("warning")

    # ── Market breadth: reduce BUY confidence in weak/poor markets ────────
    breadth_regime: str = "NEUTRAL"
    if breadth is not None:
        breadth_regime = breadth.get("regime", "NEUTRAL")
        if breadth_regime == "POOR":
            confidence = float(np.clip(confidence * 0.75, 0.0, 1.0))
        elif breadth_regime == "WEAK":
            confidence = float(np.clip(confidence * 0.88, 0.0, 1.0))
        # HEALTHY: small boost to any conviction signal
        elif breadth_regime == "HEALTHY" and abs(composite) > 0.2:
            confidence = float(np.clip(confidence * 1.05, 0.0, 1.0))

    # ── Analyst confidence boost: ±0.05 when strongly aligned ────────────
    if analyst is not None and analyst.get("total_ratings", 0) > 0:
        a_score = float(analyst.get("score", 0.0))
        if (composite > 0.1 and a_score > 0.3) or (composite < -0.1 and a_score < -0.3):
            confidence = float(np.clip(confidence + 0.05, 0.0, 1.0))

    # ── Intermarket: cross-asset headwind / tailwind modifier ─────────────
    intermarket_regime: str = "NEUTRAL"
    if intermarket is not None:
        im_score  = float(intermarket.get("score", 0.0))
        intermarket_regime = intermarket.get("regime", "NEUTRAL")
        # Blend intermarket into the composite (small 10% weight)
        composite = float(np.clip(0.90 * composite + 0.10 * im_score, -1.0, 1.0))
        # Confidence modifier: strong misalignment penalises confidence
        if intermarket_regime == "RISK_OFF" and composite > 0.1:
            confidence = float(np.clip(confidence * 0.88, 0.0, 1.0))
        elif intermarket_regime == "RISK_ON" and composite > 0.1:
            confidence = float(np.clip(confidence * 1.04, 0.0, 1.0))

    # ── Sector rotation: small tailwind / headwind from sector momentum ────
    sector_regime: str = "N/A"
    sector_name:   str = "N/A"
    if sector is not None and sector.get("regime") not in (None, "N/A"):
        sector_regime = sector.get("regime", "N/A")
        sector_name   = sector.get("sector") or "N/A"
        modifier = float(sector.get("modifier", 0.0))
        composite = float(np.clip(composite + modifier, -1.0, 1.0))

    # ── Short interest: squeeze tailwind or bearish confirmation ──────────
    short_interest_regime: str = "N/A"
    short_float_val: float | None = None
    if short_interest is not None and short_interest.get("regime") not in (None, "N/A"):
        si_score  = float(short_interest.get("score", 0.0))
        si_conf   = float(short_interest.get("confidence", 0.0))
        short_interest_regime = short_interest.get("regime", "N/A")
        short_float_val = short_interest.get("short_float")
        if si_conf > 0.3 and abs(si_score) > 0.05:
            # Small blend: 95% composite + 5% short-interest signal
            composite = float(np.clip(0.95 * composite + 0.05 * si_score, -1.0, 1.0))
            # Squeeze regime with aligned direction boosts confidence slightly
            if short_interest_regime in ("SQUEEZE", "SQUEEZE_BUILD") and composite > 0.05:
                confidence = float(np.clip(confidence + 0.04, 0.0, 1.0))

    # ── Options sentiment: PCR + IV skew (contrarian) ────────────────
    options_regime: str = "N/A"
    options_score_val: float = 0.0
    options_pcr: float | None = None
    options_iv_skew: float | None = None
    if options is not None and options.get("regime") not in (None, "N/A"):
        options_score_val = float(options.get("score", 0.0))
        options_regime    = options.get("regime", "N/A")
        options_pcr       = options.get("pcr")
        options_iv_skew   = options.get("iv_skew")
        o_conf            = float(options.get("confidence", 0.0))
        if o_conf > 0.3 and abs(options_score_val) > 0.05:
            # Blend 8% options into sentiment score (contrarian signal)
            s_score = float(np.clip(0.92 * s_score + 0.08 * options_score_val, -1.0, 1.0))
            # Confidence boost when options confirm direction
            if (options_score_val > 0.05 and composite > 0) or \
               (options_score_val < -0.05 and composite < 0):
                confidence = float(np.clip(confidence + 0.04, 0.0, 1.0))

    # ── Adaptive thresholds (regime-aware) ───────────────────────────────
    vix_lvl = None
    if macro is not None:
        _raw_vix = macro.get("vix_level")
        if _raw_vix is not None:
            try:
                vix_lvl = float(_raw_vix) if float(_raw_vix) > 0 else None
            except (TypeError, ValueError):
                pass

    adaptive = get_adaptive_thresholds(
        vix_level=vix_lvl,
        macro_regime=macro_regime if macro is not None else None,
        breadth_regime=breadth_regime,
    )
    _buy_thresh    = adaptive["buy_threshold"]
    _buy_conf_min  = adaptive["buy_conf_min"]
    _sell_thresh   = adaptive["sell_threshold"]
    _sell_conf_min = adaptive["sell_conf_min"]

    # ── Direction ─────────────────────────────────────────────────────────
    if earnings_filter is not None and earnings_filter.get("is_earnings_today"):
        direction = "HOLD"
    elif composite > _buy_thresh and confidence >= _buy_conf_min:
        direction = "BUY"
    elif composite < _sell_thresh and confidence >= _sell_conf_min:
        direction = "SELL"
    else:
        direction = "HOLD"

    # ── Risk level ────────────────────────────────────────────────────────
    abs_strength = abs(composite)
    if abs_strength > 0.5 and confidence > 0.7:
        risk_level = "LOW"
    elif abs_strength > 0.3 and confidence > 0.5:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "direction": direction,
        "strength": round(float(np.clip(composite, -1, 1)), 4),
        "confidence": round(confidence, 4),
        "risk_level": risk_level,
        "technical_score": round(t_score, 4),
        "sentiment_score": round(s_score, 4),
        "ml_score": round(m_score, 4),
        "macro_score": round(macro_score_val, 4),
        "macro_regime": macro_regime,
        "mtf_alignment": round(mtf_alignment, 4),
        "mtf_tf_scores": mtf.get("tf_scores", {}) if mtf else {},
        "earnings_warning": earnings_warning,
        "breadth_regime":      breadth_regime,
        "breadth_score":       round(float(breadth.get("score", 0.0)), 4) if breadth else 0.0,
        "analyst_score":       round(analyst_score, 4),
        "analyst_label":       analyst.get("rating_label", "N/A") if analyst else "N/A",
        "intermarket_regime":  intermarket_regime,
        "intermarket_score":   round(float(intermarket.get("score", 0.0)), 4) if intermarket else 0.0,
        "fg_score":            round(fg_score, 4),
        "fg_index":            fg_index,
        "fg_label":            fg_label,
        "sector_regime":       sector_regime,
        "sector_name":         sector_name,
        "sector_score":        round(float(sector.get("score", 0.0)), 4) if sector else 0.0,
        "short_interest_regime": short_interest_regime,
        "short_float":         short_float_val,
        "options_regime":      options_regime,
        "options_score":       round(options_score_val, 4),
        "options_pcr":         options_pcr,
        "options_iv_skew":     options_iv_skew,
        "factor_agreement": round(1.0 - score_std, 4),
        "weights_used": {k: round(v, 4) for k, v in w.items()},
        "thresholds": {
            "buy": _buy_thresh,
            "sell": _sell_thresh,
            "buy_conf_min": _buy_conf_min,
            "sell_conf_min": _sell_conf_min,
            "base_buy": BUY_THRESHOLD,
            "base_sell": SELL_THRESHOLD,
            "adjustments": adaptive.get("adjustments", []),
        },
    }


def batch_combine(signals_by_symbol: dict, macro: dict | None = None) -> list[dict]:
    """Combine signals for multiple symbols and rank them.

    Args:
        signals_by_symbol: {symbol: {"technical": ..., "sentiment": ..., "ml": ...}}
        macro: optional macro signal dict (shared across all symbols)

    Returns:
        Sorted list of combined signals (strongest first).
    """
    results = []
    for symbol, factors in signals_by_symbol.items():
        combined = combine_signals(
            factors.get("technical", {}),
            factors.get("sentiment", {}),
            factors.get("ml", {}),
            macro=macro,
        )
        combined["symbol"] = symbol
        results.append(combined)

    # Sort: BUY signals first (by strength), then HOLD, then SELL
    order = {"BUY": 0, "HOLD": 1, "SELL": 2}
    results.sort(key=lambda x: (order.get(x["direction"], 1), -abs(x["strength"])))
    return results
