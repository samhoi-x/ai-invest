"""Walk-forward backtesting validator.

Splits a price-data history into rolling in-sample / out-of-sample windows
(anchored walk-forward) and reports per-fold OOS performance metrics.
This lets you detect whether the strategy's backtested edge holds up in
successive unseen data periods.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Anchored walk-forward cross-validator for the BacktestEngine.

    For each fold *i* the engine is run on all data up to:
        ``in_sample_bars + (i + 1) * out_of_sample_bars``
    so the in-sample training window grows while each successive OOS slice
    is a fresh, unseen period.

    Args:
        in_sample_bars:     minimum bars of history before the first OOS fold
        out_of_sample_bars: size of each OOS window (bars per fold)
        initial_capital:    starting portfolio value passed to BacktestEngine
        position_size_pct:  fraction of portfolio per position
    """

    def __init__(
        self,
        in_sample_bars: int = 252,
        out_of_sample_bars: int = 63,
        initial_capital: float = 100_000.0,
        position_size_pct: float = 0.10,
    ):
        self.in_sample_bars = in_sample_bars
        self.out_of_sample_bars = out_of_sample_bars
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct

    def run(
        self,
        price_data: dict,
        signal_func=None,
        mode: str = "technical",
    ) -> dict:
        """Run anchored walk-forward validation.

        Args:
            price_data:  {symbol: DataFrame with OHLCV columns}
            signal_func: optional custom signal function(df) → dict
            mode:        "technical" or "ai" (passed to BacktestEngine.run)

        Returns:
            dict with keys:
              - folds              – list of per-fold metric dicts
              - n_folds            – total number of folds executed
              - oos_sharpe_mean    – mean OOS Sharpe across folds
              - oos_sharpe_std     – std dev of OOS Sharpe
              - oos_return_mean    – mean OOS total return
              - oos_max_dd_mean    – mean OOS max drawdown
              - oos_positive_folds – number of folds with positive return
        """
        from strategy.backtester import BacktestEngine

        # Build sorted union of all dates across all symbols
        all_dates = sorted(
            {d for df in price_data.values() for d in df.index}
        )
        total_bars = len(all_dates)

        folds: list[dict] = []
        fold_idx = 0
        oos_end = self.in_sample_bars + self.out_of_sample_bars

        while oos_end <= total_bars:
            oos_start_idx = oos_end - self.out_of_sample_bars
            window_dates = set(all_dates[:oos_end])

            # Slice each symbol's data to the current window
            window_data: dict = {}
            for sym, df in price_data.items():
                sliced = df[df.index.isin(window_dates)]
                if len(sliced) >= self.in_sample_bars + 10:
                    window_data[sym] = sliced

            if window_data:
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    position_size_pct=self.position_size_pct,
                )
                try:
                    results = engine.run(
                        window_data,
                        signal_func=signal_func,
                        mode=mode,
                    )
                    fold_metrics = {
                        "fold":          fold_idx,
                        "oos_start":     str(all_dates[oos_start_idx])[:10],
                        "oos_end":       str(all_dates[oos_end - 1])[:10],
                        "total_return":  results.get("total_return", 0.0),
                        "annual_return": results.get("annual_return", 0.0),
                        "sharpe_ratio":  results.get("sharpe_ratio", 0.0),
                        "sortino_ratio": results.get("sortino_ratio", 0.0),
                        "calmar_ratio":  results.get("calmar_ratio", 0.0),
                        "max_drawdown":  results.get("max_drawdown", 0.0),
                        "win_rate":      results.get("win_rate", 0.0),
                        "total_trades":  results.get("total_trades", 0),
                    }
                    folds.append(fold_metrics)
                    logger.debug(
                        "WF fold %d [%s→%s]: sharpe=%.3f return=%.3f dd=%.3f",
                        fold_idx,
                        fold_metrics["oos_start"],
                        fold_metrics["oos_end"],
                        fold_metrics["sharpe_ratio"],
                        fold_metrics["total_return"],
                        fold_metrics["max_drawdown"],
                    )
                except Exception as exc:
                    logger.warning("WF fold %d failed: %s", fold_idx, exc)

            oos_end += self.out_of_sample_bars
            fold_idx += 1

        if not folds:
            return {
                "folds": [],
                "n_folds": 0,
                "oos_sharpe_mean": 0.0,
                "oos_sharpe_std": 0.0,
                "oos_return_mean": 0.0,
                "oos_max_dd_mean": 0.0,
                "oos_positive_folds": 0,
            }

        sharpes = [f["sharpe_ratio"] for f in folds]
        returns = [f["total_return"] for f in folds]
        max_dds = [f["max_drawdown"] for f in folds]

        return {
            "folds":               folds,
            "n_folds":             len(folds),
            "oos_sharpe_mean":     round(float(np.mean(sharpes)), 4),
            "oos_sharpe_std":      round(float(np.std(sharpes)), 4),
            "oos_return_mean":     round(float(np.mean(returns)), 4),
            "oos_max_dd_mean":     round(float(np.mean(max_dds)), 4),
            "oos_positive_folds":  int(sum(1 for r in returns if r > 0)),
        }
