"""Event-driven backtesting engine."""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from analysis.technical import compute_technical_signal
from config import (BUY_THRESHOLD, SELL_THRESHOLD, BUY_CONFIDENCE_MIN,
                    SELL_CONFIDENCE_MIN, STOP_LOSS, RISK)

logger = logging.getLogger(__name__)


def make_ai_signal_func(symbol: str):
    """Return a signal function that combines technical + ML signals.

    Used for AI-mode backtesting.  The ML model is loaded from disk
    (trained before the backtest period starts) to avoid look-ahead bias.
    """
    from analysis.ml_models import compute_ml_signal
    from strategy.signal_combiner import combine_signals

    def _signal(df: pd.DataFrame) -> dict:
        tech = compute_technical_signal(df)
        try:
            ml = compute_ml_signal(df, symbol, train_if_needed=True)
        except Exception:
            ml = {"score": 0.0, "confidence": 0.3}
        # Neutral placeholders for signals that require live APIs
        neutral = {"score": 0.0, "confidence": 0.3}
        return combine_signals(tech, neutral, ml)

    return _signal


class BacktestEngine:
    """Event-driven backtester for signal-based strategies."""

    def __init__(self, initial_capital: float = 100000,
                 position_size_pct: float = 0.10,
                 commission: float = 0.001):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission = commission  # 0.1%

    def run(self, price_data: dict[str, pd.DataFrame],
            signal_func=None, mode: str = "technical") -> dict:
        """Run backtest across multiple assets.

        Args:
            price_data: {symbol: DataFrame with OHLCV}
            signal_func: Optional custom signal function(df) → {'score', 'confidence'}.
                         Defaults to technical analysis signal.

        Returns:
            dict with performance metrics and equity curve.
        """
        # Build per-symbol signal functions for AI mode
        if mode == "ai":
            symbol_signal_funcs = {
                sym: make_ai_signal_func(sym) for sym in price_data
            }
        else:
            # Technical-only mode: same function for all symbols
            _base_func = signal_func if signal_func is not None else compute_technical_signal
            symbol_signal_funcs = {sym: _base_func for sym in price_data}

        from analysis.technical import atr as calc_atr

        cash = self.initial_capital
        positions = {}  # symbol → {'quantity', 'entry_price', 'stop_loss'}
        trades = []
        equity_curve = []
        dates = []
        running_peak = self.initial_capital  # maintained incrementally — O(1) per step

        # Align all data to common dates
        all_dates = set()
        for sym, df in price_data.items():
            all_dates.update(df.index.tolist())
        all_dates = sorted(all_dates)

        for date in all_dates:
            # Update portfolio value
            port_value = cash
            for sym, pos in positions.items():
                if sym in price_data and date in price_data[sym].index:
                    port_value += pos["quantity"] * price_data[sym].loc[date, "close"]
                else:
                    port_value += pos["quantity"] * pos["entry_price"]

            running_peak = max(running_peak, port_value)
            equity_curve.append(port_value)
            dates.append(date)

            # Check stop losses
            closed_syms = []
            for sym, pos in positions.items():
                if sym in price_data and date in price_data[sym].index:
                    current_price = price_data[sym].loc[date, "close"]

                    # Trailing stop update
                    if current_price > pos.get("highest", pos["entry_price"]):
                        pos["highest"] = current_price
                        pos["trailing_stop"] = current_price * (1 - STOP_LOSS["trailing"])

                    # Check stops
                    stop = max(pos.get("stop_loss", 0), pos.get("trailing_stop", 0))
                    if current_price <= stop:
                        # Stop loss triggered
                        proceeds = pos["quantity"] * current_price * (1 - self.commission)
                        cash += proceeds
                        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                        trades.append({
                            "symbol": sym, "action": "SELL (STOP)",
                            "date": str(date)[:10], "price": current_price,
                            "quantity": pos["quantity"], "pnl": round(pnl, 2),
                        })
                        closed_syms.append(sym)

            for sym in closed_syms:
                del positions[sym]

            # Check drawdown protection
            current_dd = (running_peak - port_value) / running_peak if running_peak > 0 else 0
            if current_dd >= RISK["drawdown_halt"]:
                continue  # Skip new signals

            # Generate signals for each symbol
            for sym, df in price_data.items():
                if date not in df.index:
                    continue

                date_idx = df.index.get_loc(date)
                if date_idx < 200:  # Need enough history
                    continue

                history = df.iloc[:date_idx + 1]

                try:
                    sig_fn = symbol_signal_funcs.get(sym, compute_technical_signal)
                    signal = sig_fn(history)
                except Exception:
                    logger.warning("Signal computation failed for %s on %s", sym, str(date)[:10])
                    continue

                score = signal.get("score", 0)
                confidence = signal.get("confidence", 0)

                # BUY signal
                if (sym not in positions and score > BUY_THRESHOLD
                        and confidence >= BUY_CONFIDENCE_MIN):
                    price = df.loc[date, "close"]
                    position_value = port_value * self.position_size_pct
                    quantity = position_value / price
                    cost = quantity * price * (1 + self.commission)

                    if cost <= cash:
                        cash -= cost
                        # ATR-based stop loss
                        atr_val = calc_atr(history).iloc[-1]
                        stop = price - STOP_LOSS["atr_multiplier"] * atr_val if not pd.isna(atr_val) else price * 0.95

                        positions[sym] = {
                            "quantity": quantity,
                            "entry_price": price,
                            "stop_loss": stop,
                            "trailing_stop": price * (1 - STOP_LOSS["trailing"]),
                            "highest": price,
                        }
                        trades.append({
                            "symbol": sym, "action": "BUY",
                            "date": str(date)[:10], "price": price,
                            "quantity": round(quantity, 4), "pnl": 0,
                        })

                # SELL signal
                elif (sym in positions and score < SELL_THRESHOLD
                      and confidence >= SELL_CONFIDENCE_MIN):
                    price = df.loc[date, "close"]
                    pos = positions[sym]
                    proceeds = pos["quantity"] * price * (1 - self.commission)
                    cash += proceeds
                    pnl = (price - pos["entry_price"]) * pos["quantity"]
                    trades.append({
                        "symbol": sym, "action": "SELL (SIGNAL)",
                        "date": str(date)[:10], "price": price,
                        "quantity": pos["quantity"], "pnl": round(pnl, 2),
                    })
                    del positions[sym]

        # Close remaining positions at last price
        for sym, pos in positions.items():
            if sym in price_data and len(price_data[sym]) > 0:
                last_price = price_data[sym]["close"].iloc[-1]
                cash += pos["quantity"] * last_price * (1 - self.commission)
                pnl = (last_price - pos["entry_price"]) * pos["quantity"]
                trades.append({
                    "symbol": sym, "action": "CLOSE",
                    "date": str(all_dates[-1])[:10] if all_dates else "",
                    "price": last_price, "quantity": pos["quantity"],
                    "pnl": round(pnl, 2),
                })

        # Compute metrics
        metrics = self._compute_metrics(equity_curve, trades)
        metrics["equity_curve"] = equity_curve
        metrics["dates"] = [str(d)[:10] for d in dates]
        metrics["trades"] = trades

        # Buy & Hold benchmark
        benchmark = self._compute_benchmark(price_data, all_dates)
        metrics["benchmark"] = benchmark

        # Information ratio vs benchmark
        metrics["information_ratio"] = self._compute_information_ratio(
            equity_curve, benchmark
        )

        return metrics

    def _compute_metrics(self, equity_curve: list, trades: list) -> dict:
        if not equity_curve or len(equity_curve) < 2:
            return {"error": "Insufficient data"}

        initial = equity_curve[0]
        final = equity_curve[-1]
        total_return = (final / initial) - 1

        # Annualized return
        n_days = len(equity_curve)
        years = n_days / 252
        annual_return = (1 + total_return) ** (1 / max(years, 0.01)) - 1 if total_return > -1 else -1

        # Daily returns
        eq = np.array(equity_curve)
        daily_returns = np.diff(eq) / eq[:-1]

        # Sharpe ratio (annualized, rf=4%)
        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            sharpe = (np.mean(daily_returns) - 0.04 / 252) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe = 0

        # Max drawdown
        peak = np.maximum.accumulate(eq)
        drawdown = (peak - eq) / peak
        max_dd = float(np.max(drawdown))

        # Win rate
        pnl_values = [t["pnl"] for t in trades if t["action"] != "BUY"]
        wins = sum(1 for p in pnl_values if p > 0)
        total_closed = len(pnl_values)
        win_rate = wins / total_closed if total_closed > 0 else 0

        # Profit factor
        gross_profit = sum(p for p in pnl_values if p > 0)
        gross_loss = abs(sum(p for p in pnl_values if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # ── Sortino ratio (downside deviation) ───────────────────────
        if len(daily_returns) > 0:
            downside = daily_returns[daily_returns < 0]
            downside_std = float(np.std(downside)) if len(downside) > 0 else 0.0
            if downside_std > 1e-12:
                sortino = float(
                    (np.mean(daily_returns) - 0.04 / 252) / downside_std * np.sqrt(252)
                )
            elif np.std(daily_returns) > 1e-12:
                sortino = float(sharpe)  # No downside: mirror Sharpe
            else:
                sortino = 0.0
        else:
            sortino = 0.0

        # ── Calmar ratio (annual return / max drawdown) ───────────────
        calmar = round(annual_return / max_dd, 4) if max_dd > 1e-6 else 0.0

        # ── VaR and CVaR at 95 % confidence (daily returns) ──────────
        if len(daily_returns) > 0:
            var_95 = float(np.percentile(daily_returns, 5))
            tail = daily_returns[daily_returns <= var_95]
            cvar_95 = float(np.mean(tail)) if len(tail) > 0 else var_95
        else:
            var_95 = 0.0
            cvar_95 = 0.0

        return {
            "total_return":   round(total_return, 4),
            "annual_return":  round(annual_return, 4),
            "sharpe_ratio":   round(float(sharpe), 4),
            "sortino_ratio":  round(sortino, 4),
            "calmar_ratio":   round(calmar, 4),
            "max_drawdown":   round(max_dd, 4),
            "var_95":         round(var_95, 6),
            "cvar_95":        round(cvar_95, 6),
            "win_rate":       round(win_rate, 4),
            "total_trades":   total_closed,
            "profit_factor":  round(profit_factor, 4),
            "final_value":    round(final, 2),
            "initial_value":  round(initial, 2),
        }

    def _compute_information_ratio(
        self, equity_curve: list, benchmark: list
    ) -> float:
        """Annualised Information Ratio: excess return / tracking error."""
        n = min(len(equity_curve), len(benchmark))
        if n < 2:
            return 0.0
        eq = np.array(equity_curve[:n], dtype=float)
        bm = np.array(benchmark[:n], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            strat_ret = np.where(eq[:-1] > 0, np.diff(eq) / eq[:-1], 0.0)
            bench_ret = np.where(bm[:-1] > 0, np.diff(bm) / bm[:-1], 0.0)
        excess = strat_ret - bench_ret
        te = float(np.std(excess))
        if te < 1e-12:
            return 0.0
        return round(float(np.mean(excess) / te * np.sqrt(252)), 4)

    def _compute_benchmark(self, price_data: dict, dates: list) -> list:
        """Equal-weight buy & hold benchmark."""
        if not price_data or not dates:
            return []

        n_assets = len(price_data)
        alloc = self.initial_capital / n_assets
        shares = {}

        for sym, df in price_data.items():
            first_valid = df.index[0]
            close_price = df.loc[first_valid, "close"]
            if close_price == 0:
                continue
            shares[sym] = alloc / close_price

        benchmark = []
        for date in dates:
            val = 0
            for sym, df in price_data.items():
                if date in df.index:
                    val += shares[sym] * df.loc[date, "close"]
                elif benchmark:
                    val += benchmark[-1] / n_assets  # Carry forward
            benchmark.append(val if val > 0 else self.initial_capital)

        return benchmark
