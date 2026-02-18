"""Sentiment analysis using FinBERT (ProsusAI/finbert)."""

import numpy as np
import pandas as pd

# Lazy-load transformers to avoid slow startup
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
        model_name = "ProsusAI/finbert"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        _pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer,
                             truncation=True, max_length=512)
    return _pipeline


def _label_to_value(label: str, score: float) -> float:
    """Convert FinBERT label + confidence score to a signed [-1, +1] sentiment value."""
    if label == "positive":
        return score
    if label == "negative":
        return -score
    return 0.0


def analyze_text(text: str) -> dict:
    """Analyze sentiment of a single text.

    Returns:
        dict with 'label' (positive/negative/neutral), 'score' (confidence),
        and 'sentiment_value' (-1 to +1).
    """
    if not text or len(text.strip()) < 5:
        return {"label": "neutral", "score": 0.5, "sentiment_value": 0.0}

    pipe = _get_pipeline()
    result = pipe(text[:512])[0]

    label = result["label"]
    score = result["score"]
    return {
        "label": label,
        "score": score,
        "sentiment_value": round(_label_to_value(label, score), 4),
    }


def analyze_texts(texts: list[str]) -> list[dict]:
    """Analyze sentiment for a batch of texts."""
    if not texts:
        return []

    pipe = _get_pipeline()
    # Process in batches to avoid memory issues
    batch_size = 16
    results = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:512] for t in texts[i:i + batch_size] if t and len(t.strip()) >= 5]
        if batch:
            batch_results = pipe(batch)
            for text, res in zip(batch, batch_results):
                label = res["label"]
                score = res["score"]
                results.append({
                    "text": text[:100],
                    "label": label,
                    "score": score,
                    "sentiment_value": round(_label_to_value(label, score), 4),
                })
    return results


def compute_sentiment_signal(news_articles: list[dict],
                             social_texts: list[str]) -> dict:
    """Compute a composite sentiment signal from news and social data.

    Args:
        news_articles: List of dicts with 'title' and optionally 'description'
        social_texts: List of social media text strings

    Returns:
        dict with 'score' (-1 to +1), 'confidence' (0 to 1),
        'news_sentiment', 'social_sentiment', and details.
    """
    # Analyze news headlines (titles are more impactful)
    news_texts = [a["title"] for a in news_articles if a.get("title")]
    news_results = analyze_texts(news_texts) if news_texts else []

    # Analyze social media texts
    social_results = analyze_texts(social_texts) if social_texts else []

    # Compute averages
    news_values = [r["sentiment_value"] for r in news_results]
    social_values = [r["sentiment_value"] for r in social_results]

    news_avg = np.mean(news_values) if news_values else 0.0
    social_avg = np.mean(social_values) if social_values else 0.0

    # Weight news more than social (60/40)
    if news_values and social_values:
        composite = 0.6 * news_avg + 0.4 * social_avg
    elif news_values:
        composite = news_avg
    elif social_values:
        composite = social_avg
    else:
        composite = 0.0

    # Confidence based on sample size and agreement
    total_samples = len(news_values) + len(social_values)
    sample_factor = min(1.0, total_samples / 20)  # More samples = more confidence

    all_values = news_values + social_values
    if all_values:
        std = np.std(all_values)
        agreement_factor = max(0, 1.0 - std)
    else:
        agreement_factor = 0.0

    confidence = 0.3 + 0.4 * sample_factor + 0.3 * agreement_factor

    return {
        "score": round(float(np.clip(composite, -1, 1)), 4),
        "confidence": round(float(min(1.0, confidence)), 4),
        "news_sentiment": round(float(news_avg), 4),
        "social_sentiment": round(float(social_avg), 4),
        "news_count": len(news_results),
        "social_count": len(social_results),
        "details": {
            "news_results": news_results[:5],
            "social_results": social_results[:5],
        },
    }
