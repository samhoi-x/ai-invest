"""Signal explanation engine — translates raw signals into plain-language insights."""


# Self-contained bilingual strings (no dependency on i18n.py / Streamlit session)
_TEXTS = {
    "en": {
        "summary_buy": "{symbol}: Technical and AI models are bullish. {strongest_factor}. Confidence {confidence:.0%}. Suggested action: BUY.",
        "summary_sell": "{symbol}: Indicators point downward. {strongest_factor}. Confidence {confidence:.0%}. Suggested action: SELL.",
        "summary_hold": "{symbol}: Mixed or neutral signals. {strongest_factor}. Confidence {confidence:.0%}. Suggested action: HOLD.",
        "dir_buy": "Multiple factors lean bullish — the weighted composite score exceeds the buy threshold with sufficient confidence.",
        "dir_sell": "Multiple factors lean bearish — the weighted composite score falls below the sell threshold.",
        "dir_hold": "Signals are mixed or too weak to commit — staying on the sidelines is the safer choice.",
        "factor_tech_pos": "Technical analysis is bullish (score {score:+.2f}): price trends and indicators favour upside.",
        "factor_tech_neg": "Technical analysis is bearish (score {score:+.2f}): price trends and indicators favour downside.",
        "factor_tech_neutral": "Technical analysis is neutral (score {score:+.2f}): no clear directional bias.",
        "factor_sent_pos": "Market sentiment is optimistic (score {score:+.2f}): news and social media lean positive.",
        "factor_sent_neg": "Market sentiment is pessimistic (score {score:+.2f}): news and social media lean negative.",
        "factor_sent_neutral": "Market sentiment is neutral (score {score:+.2f}): no strong mood detected.",
        "factor_ml_pos": "AI models predict an upward move (score {score:+.2f}) over the next 5 trading days.",
        "factor_ml_neg": "AI models predict a downward move (score {score:+.2f}) over the next 5 trading days.",
        "factor_ml_neutral": "AI models show no strong prediction (score {score:+.2f}).",
        "rsi_oversold": "RSI is at {value:.0f} — in oversold territory. Historically, this often precedes a bounce.",
        "rsi_overbought": "RSI is at {value:.0f} — in overbought territory. Price may face pullback pressure.",
        "rsi_normal": "RSI is at {value:.0f} — within the normal range.",
        "macd_bullish": "MACD ({value:+.4f}) is positive, suggesting bullish momentum.",
        "macd_bearish": "MACD ({value:+.4f}) is negative, suggesting bearish momentum.",
        "bb_low": "Price is near the lower Bollinger Band (BB% {value:.0%}), potentially undervalued.",
        "bb_high": "Price is near the upper Bollinger Band (BB% {value:.0%}), potentially overextended.",
        "bb_mid": "Price is within the Bollinger Bands (BB% {value:.0%}), indicating normal volatility.",
        "ma_bullish": "Price (${price:.2f}) is above both SMA-20 (${sma20:.2f}) and SMA-50 (${sma50:.2f}) — uptrend.",
        "ma_bearish": "Price (${price:.2f}) is below both SMA-20 (${sma20:.2f}) and SMA-50 (${sma50:.2f}) — downtrend.",
        "ma_mixed": "Price (${price:.2f}) is between SMA-20 (${sma20:.2f}) and SMA-50 (${sma50:.2f}) — trend is unclear.",
        "agreement_high": "All three factors (technical / sentiment / AI) agree on direction — higher reliability.",
        "agreement_low": "Factors disagree — confidence has been reduced. Proceed with caution.",
        "risk_low": "Risk level: LOW — strong signal with high confidence.",
        "risk_medium": "Risk level: MEDIUM — moderate signal strength or confidence.",
        "risk_high": "Risk level: HIGH — weak signal or low confidence; consider smaller position size.",
        "conf_high": "Confidence {value:.0%} — the model is quite sure about this signal.",
        "conf_medium": "Confidence {value:.0%} — moderate certainty; some uncertainty remains.",
        "conf_low": "Confidence {value:.0%} — low certainty; treat this as a weak hint rather than a firm call.",
        "strongest_tech": "Technical analysis is the strongest factor",
        "strongest_sent": "Sentiment is the strongest factor",
        "strongest_ml": "AI model prediction is the strongest factor",
    },
    "zh": {
        "summary_buy": "{symbol}：技術面與 AI 模型均看好。{strongest_factor}。信心度 {confidence:.0%}。建議買入。",
        "summary_sell": "{symbol}：指標偏向下行。{strongest_factor}。信心度 {confidence:.0%}。建議賣出。",
        "summary_hold": "{symbol}：信號混合或中性。{strongest_factor}。信心度 {confidence:.0%}。建議觀望。",
        "dir_buy": "多個因子偏向看漲——加權綜合分數超過買入門檻，且信心度達標。",
        "dir_sell": "多個因子偏向看跌——加權綜合分數低於賣出門檻。",
        "dir_hold": "信號混合或過弱，無法做出明確判斷——保持觀望較為安全。",
        "factor_tech_pos": "技術分析看漲（分數 {score:+.2f}）：價格趨勢和指標偏向上行。",
        "factor_tech_neg": "技術分析看跌（分數 {score:+.2f}）：價格趨勢和指標偏向下行。",
        "factor_tech_neutral": "技術分析中性（分數 {score:+.2f}）：無明確方向偏好。",
        "factor_sent_pos": "市場情緒樂觀（分數 {score:+.2f}）：新聞和社群媒體偏正面。",
        "factor_sent_neg": "市場情緒悲觀（分數 {score:+.2f}）：新聞和社群媒體偏負面。",
        "factor_sent_neutral": "市場情緒中性（分數 {score:+.2f}）：未偵測到強烈情緒。",
        "factor_ml_pos": "AI 模型預測未來 5 個交易日上漲（分數 {score:+.2f}）。",
        "factor_ml_neg": "AI 模型預測未來 5 個交易日下跌（分數 {score:+.2f}）。",
        "factor_ml_neutral": "AI 模型無強烈預測（分數 {score:+.2f}）。",
        "rsi_oversold": "RSI 在 {value:.0f}，處於超賣區間，歷史上常出現反彈機會。",
        "rsi_overbought": "RSI 在 {value:.0f}，處於超買區間，價格可能面臨回調壓力。",
        "rsi_normal": "RSI 在 {value:.0f}，處於正常範圍。",
        "macd_bullish": "MACD（{value:+.4f}）為正值，暗示看漲動能。",
        "macd_bearish": "MACD（{value:+.4f}）為負值，暗示看跌動能。",
        "bb_low": "價格接近布林通道下軌（BB% {value:.0%}），可能被低估。",
        "bb_high": "價格接近布林通道上軌（BB% {value:.0%}），可能過度延伸。",
        "bb_mid": "價格在布林通道內（BB% {value:.0%}），波動性正常。",
        "ma_bullish": "股價（${price:.2f}）高於 SMA-20（${sma20:.2f}）和 SMA-50（${sma50:.2f}）——上升趨勢。",
        "ma_bearish": "股價（${price:.2f}）低於 SMA-20（${sma20:.2f}）和 SMA-50（${sma50:.2f}）——下降趨勢。",
        "ma_mixed": "股價（${price:.2f}）介於 SMA-20（${sma20:.2f}）和 SMA-50（${sma50:.2f}）之間——趨勢不明。",
        "agreement_high": "三個因子（技術面/情緒面/AI 模型）方向一致——可靠度較高。",
        "agreement_low": "因子之間存在分歧——信心度已下調，建議謹慎操作。",
        "risk_low": "風險等級：低——信號強且信心度高。",
        "risk_medium": "風險等級：中——信號強度或信心度適中。",
        "risk_high": "風險等級：高——信號弱或信心度低，建議縮小倉位。",
        "conf_high": "信心度 {value:.0%}——模型對此信號相當有把握。",
        "conf_medium": "信心度 {value:.0%}——中等確定性，仍有一些不確定因素。",
        "conf_low": "信心度 {value:.0%}——確定性低，請視為弱暗示而非明確指令。",
        "strongest_tech": "技術分析是最強因子",
        "strongest_sent": "情緒分析是最強因子",
        "strongest_ml": "AI 模型預測是最強因子",
    },
}


def _txt(key: str, lang: str, **kwargs) -> str:
    """Fetch a bilingual text template and format it."""
    template = _TEXTS.get(lang, _TEXTS["en"]).get(key, _TEXTS["en"].get(key, key))
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def _explain_factor(name: str, score: float, lang: str) -> str:
    """Return a plain-language explanation for a single factor."""
    if score > 0.1:
        tone = "pos"
    elif score < -0.1:
        tone = "neg"
    else:
        tone = "neutral"
    return _txt(f"factor_{name}_{tone}", lang, score=score)


def _strongest_factor(combined: dict, lang: str) -> str:
    """Identify and describe the strongest factor."""
    factors = {
        "tech": abs(combined.get("technical_score", 0)),
        "sent": abs(combined.get("sentiment_score", 0)),
        "ml": abs(combined.get("ml_score", 0)),
    }
    best = max(factors, key=factors.get)
    return _txt(f"strongest_{best}", lang)


def _explain_indicators(tech_signal: dict, lang: str) -> list[str]:
    """Generate plain-language explanations for each technical indicator."""
    indicators = tech_signal.get("indicators", {})
    explanations = []

    # RSI
    rsi = indicators.get("RSI", 50)
    if rsi < 30:
        explanations.append(_txt("rsi_oversold", lang, value=rsi))
    elif rsi > 70:
        explanations.append(_txt("rsi_overbought", lang, value=rsi))
    else:
        explanations.append(_txt("rsi_normal", lang, value=rsi))

    # MACD
    macd = indicators.get("MACD", 0)
    if macd > 0:
        explanations.append(_txt("macd_bullish", lang, value=macd))
    else:
        explanations.append(_txt("macd_bearish", lang, value=macd))

    # Bollinger Band %
    bb_pct = indicators.get("BB_pct", 0.5)
    if bb_pct < 0.2:
        explanations.append(_txt("bb_low", lang, value=bb_pct))
    elif bb_pct > 0.8:
        explanations.append(_txt("bb_high", lang, value=bb_pct))
    else:
        explanations.append(_txt("bb_mid", lang, value=bb_pct))

    # Moving average trend
    sma20 = indicators.get("SMA_20", 0)
    sma50 = indicators.get("SMA_50", 0)
    # Use the last close from indicators if available, else use SMA_20 as proxy
    price = indicators.get("close", sma20)
    if sma20 > 0 and sma50 > 0 and price > 0:
        if price > sma20 and price > sma50:
            explanations.append(_txt("ma_bullish", lang, price=price, sma20=sma20, sma50=sma50))
        elif price < sma20 and price < sma50:
            explanations.append(_txt("ma_bearish", lang, price=price, sma20=sma20, sma50=sma50))
        else:
            explanations.append(_txt("ma_mixed", lang, price=price, sma20=sma20, sma50=sma50))

    return explanations


def explain_signal(combined: dict, tech_signal: dict, lang: str = "en") -> dict:
    """Translate combine_signals() and compute_technical_signal() output
    into beginner-friendly explanations.

    Args:
        combined: Output of combine_signals().
        tech_signal: Output of compute_technical_signal().
        lang: "en" or "zh".

    Returns:
        dict with summary, direction_reason, factor_explanations,
        indicator_explanations, risk_explanation, confidence_explanation.
    """
    direction = combined.get("direction", "HOLD")
    confidence = combined.get("confidence", 0)
    symbol = combined.get("symbol", "")

    # --- Summary ---
    strongest = _strongest_factor(combined, lang)
    summary_key = f"summary_{direction.lower()}"
    summary = _txt(summary_key, lang, symbol=symbol, strongest_factor=strongest,
                   confidence=confidence)

    # --- Direction reason ---
    direction_reason = _txt(f"dir_{direction.lower()}", lang)

    # --- Factor explanations ---
    factor_explanations = [
        _explain_factor("tech", combined.get("technical_score", 0), lang),
        _explain_factor("sent", combined.get("sentiment_score", 0), lang),
        _explain_factor("ml", combined.get("ml_score", 0), lang),
    ]

    # Factor agreement note
    agreement = combined.get("factor_agreement", 0.5)
    if agreement >= 0.7:
        factor_explanations.append(_txt("agreement_high", lang))
    elif agreement < 0.5:
        factor_explanations.append(_txt("agreement_low", lang))

    # --- Indicator explanations ---
    indicator_explanations = _explain_indicators(tech_signal, lang)

    # --- Risk explanation ---
    risk_level = combined.get("risk_level", "HIGH")
    risk_explanation = _txt(f"risk_{risk_level.lower()}", lang)

    # --- Confidence explanation ---
    if confidence >= 0.7:
        conf_key = "conf_high"
    elif confidence >= 0.5:
        conf_key = "conf_medium"
    else:
        conf_key = "conf_low"
    confidence_explanation = _txt(conf_key, lang, value=confidence)

    return {
        "summary": summary,
        "direction_reason": direction_reason,
        "factor_explanations": factor_explanations,
        "indicator_explanations": indicator_explanations,
        "risk_explanation": risk_explanation,
        "confidence_explanation": confidence_explanation,
    }
