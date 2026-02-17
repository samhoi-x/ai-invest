"""Multi-factor signal fusion engine."""

import numpy as np
from config import (SIGNAL_WEIGHTS, BUY_THRESHOLD, BUY_CONFIDENCE_MIN,
                    SELL_THRESHOLD, SELL_CONFIDENCE_MIN)


def combine_signals(technical: dict, sentiment: dict, ml: dict) -> dict:
    """Combine three signal sources into a final recommendation.

    Args:
        technical: dict with 'score' (-1 to +1) and 'confidence'
        sentiment: dict with 'score' (-1 to +1) and 'confidence'
        ml: dict with 'score' (-1 to +1) and 'confidence'

    Returns:
        dict with 'direction' (BUY/SELL/HOLD), 'strength' (-1 to +1),
        'confidence' (0 to 1), and factor breakdown.
    """
    w = SIGNAL_WEIGHTS

    t_score = technical.get("score", 0)
    s_score = sentiment.get("score", 0)
    m_score = ml.get("score", 0)

    t_conf = technical.get("confidence", 0)
    s_conf = sentiment.get("confidence", 0)
    m_conf = ml.get("confidence", 0)

    # Weighted composite score
    composite = (w["technical"] * t_score +
                 w["sentiment"] * s_score +
                 w["ml"] * m_score)

    # Confidence: weighted average of factor confidences, penalized by disagreement
    base_confidence = (w["technical"] * t_conf +
                       w["sentiment"] * s_conf +
                       w["ml"] * m_conf)

    # Measure factor agreement/divergence
    scores = [t_score, s_score, m_score]
    score_std = np.std(scores)
    directions = [np.sign(s) if abs(s) > 0.05 else 0 for s in scores]
    disagreement_count = len(set(d for d in directions if d != 0))

    # Penalize confidence when factors disagree
    if disagreement_count >= 2:
        divergence_penalty = 0.3  # Big penalty for opposing signals
    elif score_std > 0.3:
        divergence_penalty = 0.15
    else:
        divergence_penalty = 0.0

    confidence = max(0.0, min(1.0, base_confidence - divergence_penalty))

    # Determine direction with conservative bias
    if composite > BUY_THRESHOLD and confidence >= BUY_CONFIDENCE_MIN:
        direction = "BUY"
    elif composite < SELL_THRESHOLD and confidence >= SELL_CONFIDENCE_MIN:
        direction = "SELL"
    else:
        direction = "HOLD"

    # Risk level
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
        "factor_agreement": round(1.0 - score_std, 4),
        "thresholds": {
            "buy": BUY_THRESHOLD,
            "sell": SELL_THRESHOLD,
            "buy_conf_min": BUY_CONFIDENCE_MIN,
            "sell_conf_min": SELL_CONFIDENCE_MIN,
        },
    }


def batch_combine(signals_by_symbol: dict) -> list[dict]:
    """Combine signals for multiple symbols and rank them.

    Args:
        signals_by_symbol: {symbol: {"technical": ..., "sentiment": ..., "ml": ...}}

    Returns:
        Sorted list of combined signals (strongest first).
    """
    results = []
    for symbol, factors in signals_by_symbol.items():
        combined = combine_signals(
            factors.get("technical", {}),
            factors.get("sentiment", {}),
            factors.get("ml", {}),
        )
        combined["symbol"] = symbol
        results.append(combined)

    # Sort: BUY signals first (by strength), then HOLD, then SELL
    order = {"BUY": 0, "HOLD": 1, "SELL": 2}
    results.sort(key=lambda x: (order.get(x["direction"], 1), -abs(x["strength"])))
    return results
