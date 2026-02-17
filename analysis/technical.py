"""Technical analysis indicators and signal scoring."""

import pandas as pd
import numpy as np
from config import TECH_PARAMS


# ══════════════════════════════════════════════════════════════════════
#  Individual Indicators
# ══════════════════════════════════════════════════════════════════════

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20,
                    std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = sma(series, period)
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def stochastic(df: pd.DataFrame, k_period: int = 14,
               d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    low_min = df["low"].rolling(window=k_period).min()
    high_max = df["high"].rolling(window=k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(window=d_period).mean()
    return k, d


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff())
    direction.iloc[0] = 0
    return (direction * df["volume"]).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


# ══════════════════════════════════════════════════════════════════════
#  Compute All Indicators
# ══════════════════════════════════════════════════════════════════════

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicator columns to a DataFrame."""
    p = TECH_PARAMS
    result = df.copy()

    # Moving averages
    for period in p["sma_periods"]:
        result[f"SMA_{period}"] = sma(df["close"], period)
    for period in p["ema_periods"]:
        result[f"EMA_{period}"] = ema(df["close"], period)

    # RSI
    result["RSI"] = rsi(df["close"], p["rsi_period"])

    # MACD
    macd_line, signal_line, hist = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    result["MACD"] = macd_line
    result["MACD_signal"] = signal_line
    result["MACD_hist"] = hist

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = bollinger_bands(df["close"], p["bb_period"], p["bb_std"])
    result["BB_upper"] = bb_upper
    result["BB_middle"] = bb_middle
    result["BB_lower"] = bb_lower
    result["BB_pct"] = (df["close"] - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # ATR
    result["ATR"] = atr(df, p["atr_period"])

    # Stochastic
    k, d = stochastic(df, p["stoch_k"], p["stoch_d"])
    result["Stoch_K"] = k
    result["Stoch_D"] = d

    # Volume indicators
    result["OBV"] = obv(df)
    if df["volume"].sum() > 0:
        result["VWAP"] = vwap(df)

    return result


# ══════════════════════════════════════════════════════════════════════
#  Signal Scoring (-1.0 to +1.0)
# ══════════════════════════════════════════════════════════════════════

def score_rsi(rsi_val: float) -> float:
    """Score RSI: oversold → buy, overbought → sell."""
    if pd.isna(rsi_val):
        return 0.0
    if rsi_val < 30:
        return 0.5 + (30 - rsi_val) / 60  # 0.5 to 1.0
    elif rsi_val > 70:
        return -0.5 - (rsi_val - 70) / 60  # -0.5 to -1.0
    else:
        return (50 - rsi_val) / 40  # Slight bias around neutral


def score_macd(macd_val: float, signal_val: float, hist: float) -> float:
    if pd.isna(macd_val) or pd.isna(signal_val):
        return 0.0
    # Crossover direction
    if hist > 0:
        return min(1.0, hist / (abs(signal_val) + 1e-8) * 0.5)
    else:
        return max(-1.0, hist / (abs(signal_val) + 1e-8) * 0.5)


def score_bollinger(close: float, upper: float, lower: float, bb_pct: float) -> float:
    if pd.isna(bb_pct):
        return 0.0
    if bb_pct < 0.1:
        return 0.6  # Near lower band → buy
    elif bb_pct > 0.9:
        return -0.6  # Near upper band → sell
    else:
        return (0.5 - bb_pct) * 0.8


def score_ma_trend(close: float, sma_20: float, sma_50: float, sma_200: float) -> float:
    score = 0.0
    if not pd.isna(sma_20):
        score += 0.2 if close > sma_20 else -0.2
    if not pd.isna(sma_50):
        score += 0.2 if close > sma_50 else -0.2
    if not pd.isna(sma_200):
        score += 0.3 if close > sma_200 else -0.3
    if not pd.isna(sma_20) and not pd.isna(sma_50):
        score += 0.15 if sma_20 > sma_50 else -0.15
    return max(-1.0, min(1.0, score))


def score_stochastic(k: float, d: float) -> float:
    if pd.isna(k) or pd.isna(d):
        return 0.0
    if k < 20 and d < 20:
        return 0.5
    elif k > 80 and d > 80:
        return -0.5
    elif k > d:
        return 0.2
    else:
        return -0.2


def compute_technical_signal(df: pd.DataFrame) -> dict:
    """Compute a composite technical signal from the latest data point.

    Returns:
        dict with 'score' (-1 to +1), 'confidence' (0 to 1), and
        individual indicator scores.
    """
    indicators = compute_all_indicators(df)
    latest = indicators.iloc[-1]

    scores = {
        "rsi": score_rsi(latest.get("RSI", 50)),
        "macd": score_macd(latest.get("MACD", 0), latest.get("MACD_signal", 0), latest.get("MACD_hist", 0)),
        "bollinger": score_bollinger(latest["close"], latest.get("BB_upper", 0),
                                     latest.get("BB_lower", 0), latest.get("BB_pct", 0.5)),
        "ma_trend": score_ma_trend(latest["close"], latest.get("SMA_20", np.nan),
                                   latest.get("SMA_50", np.nan), latest.get("SMA_200", np.nan)),
        "stochastic": score_stochastic(latest.get("Stoch_K", 50), latest.get("Stoch_D", 50)),
    }

    # Weighted average
    weights = {"rsi": 0.20, "macd": 0.25, "bollinger": 0.15, "ma_trend": 0.25, "stochastic": 0.15}
    composite = sum(scores[k] * weights[k] for k in scores)

    # Confidence: based on agreement among indicators
    directions = [1 if s > 0.1 else -1 if s < -0.1 else 0 for s in scores.values()]
    non_neutral = [d for d in directions if d != 0]
    if non_neutral:
        agreement = abs(sum(non_neutral)) / len(non_neutral)
    else:
        agreement = 0.0
    confidence = min(1.0, 0.4 + agreement * 0.6)

    return {
        "score": round(max(-1.0, min(1.0, composite)), 4),
        "confidence": round(confidence, 4),
        "details": {k: round(v, 4) for k, v in scores.items()},
        "indicators": {
            "RSI": round(latest.get("RSI", 0), 2),
            "MACD": round(latest.get("MACD", 0), 4),
            "BB_pct": round(latest.get("BB_pct", 0.5), 4),
            "SMA_20": round(latest.get("SMA_20", 0), 2),
            "SMA_50": round(latest.get("SMA_50", 0), 2),
            "ATR": round(latest.get("ATR", 0), 4),
        },
    }
