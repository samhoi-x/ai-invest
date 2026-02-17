"""Event-driven backtesting engine."""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from analysis.technical import compute_technical_signal
from config import (BUY_THRESHOLD, SELL_THRESHOLD, BUY_CONFIDENCE_MIN,
                    SELL_CONFIDENCE_MIN, STOP_LOSS, RISK)

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Event-driven backtester for signal-based strategies."""

    def __init__(self, initial_capital: float = 100000,
                 position_size_pct: float = 0.10,
                 commission: float = 0.001):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission = commission  # 0.1%

    def run(self, price_data: dict[str, pd.DataFrame],
            signal_func=None) -> dict:
        """Run backtest across multiple assets.

        Args:
            price_data: {symbol: DataFrame with OHLCV}
            signal_func: Optional custom signal function(df) → {'score', 'confidence'}.
                         Defaults to technical analysis signal.

        Returns:
            dict with performance metrics and equity curve.
        """
        if signal_func is None:
            signal_func = compute_technical_signal

        cash = self.initial_capital
        positions = {}  # symbol → {'quantity', 'entry_price', 'stop_loss'}
        trades = []
        equity_curve = []
        dates = []

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
            if equity_curve:
                peak = max(equity_curve)
                current_dd = (peak - port_value) / peak
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
                    signal = signal_func(history)
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
                        from analysis.technical import atr as calc_atr
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
        metrics["benchmark"] = self._compute_benchmark(price_data, all_dates)

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

        return {
            "total_return": round(total_return, 4),
            "annual_return": round(annual_return, 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 4),
            "total_trades": total_closed,
            "profit_factor": round(profit_factor, 4),
            "final_value": round(final, 2),
            "initial_value": round(initial, 2),
        }

    def _compute_benchmark(self, price_data: dict, dates: list) -> list:
        """Equal-weight buy & hold benchmark."""
        if not price_data or not dates:
            return []

        n_assets = len(price_data)
        alloc = self.initial_capital / n_assets
        shares = {}

        for sym, df in price_data.items():
            first_valid = df.index[0]
            shares[sym] = alloc / df.loc[first_valid, "close"]

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
