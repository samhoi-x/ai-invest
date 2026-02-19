"""Monte Carlo simulation for backtest robustness analysis.

Bootstrap-shuffles the observed trade P&L sequence N times to estimate
confidence intervals on key performance metrics.  This answers: "how much
of our backtest result is due to the *order* of our trades (luck) versus
the actual edge?"
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


def run_monte_carlo(
    trade_returns: list,
    initial_capital: float = 100_000.0,
    n_simulations: int = 1_000,
    random_seed: int | None = 42,
) -> dict:
    """Bootstrap-shuffle Monte Carlo simulation of equity curves.

    Randomly reorders the observed trade P&L sequence ``n_simulations``
    times.  For each shuffle an equity curve is built and key metrics are
    computed, producing percentile distributions that show the range of
    plausible outcomes given the same set of trades in a different order.

    Args:
        trade_returns:  list of individual trade P&L values (dollars)
        initial_capital: starting portfolio value
        n_simulations:  number of random shuffles
        random_seed:    reproducibility seed (None = non-deterministic)

    Returns:
        dict with keys:
          - n_simulations            – number of simulations run
          - n_trades                 – number of trades in input
          - total_return             – {p5, p25, p50, p75, p95}
          - max_drawdown             – {p5, p25, p50, p75, p95}
          - sharpe_ratio             – {p5, p25, p50, p75, p95}
          - final_value              – {p5, p25, p50, p75, p95}
          - prob_positive            – fraction of sims with positive return
          - prob_drawdown_over_20pct – fraction of sims with max DD > 20 %
    """
    if not trade_returns:
        return _empty_result()

    rng = np.random.default_rng(random_seed)
    arr = np.array(trade_returns, dtype=float)
    n_trades = len(arr)

    sim_total_returns = np.empty(n_simulations)
    sim_max_dds       = np.empty(n_simulations)
    sim_sharpes       = np.empty(n_simulations)
    sim_final_values  = np.empty(n_simulations)

    for i in range(n_simulations):
        shuffled = rng.permutation(arr)
        equity   = _build_equity_curve(shuffled, initial_capital)

        sim_total_returns[i] = (equity[-1] - equity[0]) / equity[0]
        sim_max_dds[i]       = _max_drawdown(equity)
        sim_sharpes[i]       = _sharpe(equity)
        sim_final_values[i]  = equity[-1]

    pcts = [5, 25, 50, 75, 95]
    result = {
        "n_simulations":            n_simulations,
        "n_trades":                 n_trades,
        "total_return":             _pct_dict(sim_total_returns, pcts),
        "max_drawdown":             _pct_dict(sim_max_dds, pcts),
        "sharpe_ratio":             _pct_dict(sim_sharpes, pcts),
        "final_value":              _pct_dict(sim_final_values, pcts),
        "prob_positive":            round(float(np.mean(sim_total_returns > 0)), 4),
        "prob_drawdown_over_20pct": round(float(np.mean(sim_max_dds > 0.20)), 4),
    }

    logger.debug(
        "Monte Carlo (%d sims, %d trades): return p50=%.3f dd p95=%.3f prob_pos=%.2f",
        n_simulations, n_trades,
        result["total_return"]["p50"],
        result["max_drawdown"]["p95"],
        result["prob_positive"],
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────

def _build_equity_curve(pnl_arr: np.ndarray, initial: float) -> np.ndarray:
    """Cumulative equity curve from a trade P&L array."""
    equity = np.empty(len(pnl_arr) + 1)
    equity[0] = initial
    np.cumsum(pnl_arr, out=equity[1:])
    equity[1:] += initial
    return equity


def _max_drawdown(equity: np.ndarray) -> float:
    """Peak-to-trough max drawdown of an equity curve."""
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
    return float(np.max(dd))


def _sharpe(equity: np.ndarray, rf: float = 0.04) -> float:
    """Annualised Sharpe ratio (assuming daily bars, rf = 4 %)."""
    if len(equity) < 2:
        return 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        daily_ret = np.where(
            equity[:-1] != 0,
            np.diff(equity) / equity[:-1],
            0.0,
        )
    std = float(np.std(daily_ret))
    if std < 1e-12:
        return 0.0
    return float((np.mean(daily_ret) - rf / 252) / std * np.sqrt(252))


def _pct_dict(arr: np.ndarray, percentiles: list) -> dict:
    return {f"p{p}": round(float(np.percentile(arr, p)), 4) for p in percentiles}


def _empty_result() -> dict:
    return {
        "n_simulations":            0,
        "n_trades":                 0,
        "total_return":             {},
        "max_drawdown":             {},
        "sharpe_ratio":             {},
        "final_value":              {},
        "prob_positive":            0.0,
        "prob_drawdown_over_20pct": 0.0,
    }
