"""Portfolio optimization using PyPortfolioOpt."""

import pandas as pd
import numpy as np
from config import RISK


def optimize_portfolio(returns: pd.DataFrame,
                       method: str = "min_volatility") -> dict:
    """Optimize portfolio weights.

    Args:
        returns: DataFrame of daily returns (columns = symbols)
        method: 'min_volatility', 'max_sharpe', or 'efficient_risk'

    Returns:
        dict with 'weights', 'expected_return', 'volatility', 'sharpe'.
    """
    from pypfopt import EfficientFrontier, risk_models, expected_returns

    if returns.empty or len(returns.columns) < 2:
        return {"error": "Need at least 2 assets for optimization"}

    # Clean data
    returns = returns.dropna(axis=1, how="all").dropna()
    if len(returns) < 60:
        return {"error": "Insufficient data (need at least 60 days)"}

    mu = expected_returns.mean_historical_return(returns, frequency=252,
                                                  compounding=False)
    cov = risk_models.sample_cov(returns, frequency=252)

    ef = EfficientFrontier(mu, cov, weight_bounds=(0, RISK["max_single_position"]))

    try:
        if method == "min_volatility":
            ef.min_volatility()
        elif method == "max_sharpe":
            ef.max_sharpe(risk_free_rate=0.04)
        elif method == "efficient_risk":
            ef.efficient_risk(target_volatility=0.15)
        else:
            ef.min_volatility()
    except Exception as e:
        return {"error": f"Optimization failed: {e}"}

    weights = ef.clean_weights()
    perf = ef.portfolio_performance(risk_free_rate=0.04)

    return {
        "weights": {k: round(v, 4) for k, v in weights.items() if v > 0.001},
        "expected_annual_return": round(perf[0], 4),
        "annual_volatility": round(perf[1], 4),
        "sharpe_ratio": round(perf[2], 4),
        "method": method,
    }


def get_rebalance_suggestions(current_weights: dict[str, float],
                              optimal_weights: dict[str, float],
                              portfolio_value: float) -> list[dict]:
    """Generate rebalancing suggestions.

    Args:
        current_weights: Current allocation {symbol: weight}
        optimal_weights: Target allocation from optimizer
        portfolio_value: Total portfolio value

    Returns:
        List of suggested trades to reach target allocation.
    """
    all_symbols = set(list(current_weights.keys()) + list(optimal_weights.keys()))
    suggestions = []

    for symbol in sorted(all_symbols):
        current = current_weights.get(symbol, 0)
        target = optimal_weights.get(symbol, 0)
        diff = target - current

        if abs(diff) < 0.01:  # Skip tiny differences
            continue

        trade_value = diff * portfolio_value

        suggestions.append({
            "symbol": symbol,
            "current_weight": round(current, 4),
            "target_weight": round(target, 4),
            "diff": round(diff, 4),
            "action": "BUY" if diff > 0 else "SELL",
            "trade_value": round(abs(trade_value), 2),
        })

    suggestions.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return suggestions


def build_returns_from_prices(price_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a returns DataFrame from price DataFrames.

    Args:
        price_data: {symbol: DataFrame with 'close' column}

    Returns:
        DataFrame of daily returns.
    """
    close_prices = {}
    for symbol, df in price_data.items():
        if "close" in df.columns:
            close_prices[symbol] = df["close"]

    if not close_prices:
        return pd.DataFrame()

    prices_df = pd.DataFrame(close_prices)
    returns = prices_df.pct_change().dropna()
    return returns
