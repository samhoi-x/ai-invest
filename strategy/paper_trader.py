"""Paper Trading Engine.

Simulates real-time trade execution against live signals without using
real money.  Positions, trades, and portfolio state are persisted in the
SQLite database so they survive app restarts.

Dependency injection is supported for all DB operations so the class can
be tested with in-memory lists instead of a real database.
"""

import logging
from datetime import datetime
from typing import Callable

from config import STOP_LOSS, BUY_THRESHOLD, BUY_CONFIDENCE_MIN, SELL_THRESHOLD

logger = logging.getLogger(__name__)

# Default DB accessors (overridable for testing)
def _default_get_positions(status="open"):
    from db.models import get_paper_positions
    return get_paper_positions(status)

def _default_open_position(symbol, entry_price, quantity, stop_loss=None):
    from db.models import open_paper_position
    return open_paper_position(symbol, entry_price, quantity, stop_loss)

def _default_update_position(position_id, **kwargs):
    from db.models import update_paper_position
    return update_paper_position(position_id, **kwargs)

def _default_close_position(position_id, close_price, realized_pnl):
    from db.models import close_paper_position
    return close_paper_position(position_id, close_price, realized_pnl)

def _default_add_trade(symbol, action, price, quantity, pnl=0, reason=""):
    from db.models import add_paper_trade
    return add_paper_trade(symbol, action, price, quantity, pnl, reason)

def _default_get_trades(limit=200):
    from db.models import get_paper_trades
    return get_paper_trades(limit)

def _default_reset():
    from db.models import reset_paper_portfolio
    return reset_paper_portfolio()


class PaperTrader:
    """Virtual portfolio that auto-executes AI signals on paper.

    Args:
        initial_capital:   Starting virtual cash (default 100 000).
        position_size_pct: Fraction of total portfolio per new position (default 10 %).
        commission:        Round-trip commission rate (default 0.1 %).
        get_positions_fn:  Injected function — returns list of position dicts.
        open_position_fn:  Injected function — opens a new position, returns id.
        update_position_fn: Injected function — updates position fields.
        close_position_fn: Injected function — marks position as closed.
        add_trade_fn:      Injected function — logs a trade.
        get_trades_fn:     Injected function — returns list of trade dicts.
        reset_fn:          Injected function — wipes all positions and trades.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        position_size_pct: float = 0.10,
        commission: float = 0.001,
        get_positions_fn: Callable | None = None,
        open_position_fn: Callable | None = None,
        update_position_fn: Callable | None = None,
        close_position_fn: Callable | None = None,
        add_trade_fn: Callable | None = None,
        get_trades_fn: Callable | None = None,
        reset_fn: Callable | None = None,
    ):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission = commission

        # Inject or use real DB accessors
        self._get_positions  = get_positions_fn  or _default_get_positions
        self._open_position  = open_position_fn  or _default_open_position
        self._update_position = update_position_fn or _default_update_position
        self._close_position = close_position_fn or _default_close_position
        self._add_trade      = add_trade_fn      or _default_add_trade
        self._get_trades     = get_trades_fn     or _default_get_trades
        self._reset          = reset_fn          or _default_reset

    # ── Public API ────────────────────────────────────────────────────

    def process_signal(
        self,
        symbol: str,
        signal: dict,
        current_price: float,
        atr: float | None = None,
    ) -> str | None:
        """Open or close a virtual position based on the signal.

        Args:
            symbol:        Trading symbol (e.g. "AAPL").
            signal:        Output of combine_signals() — must contain
                           'direction', 'strength', 'confidence'.
            current_price: Latest market price.
            atr:           Average True Range for stop calculation (optional).

        Returns:
            Action taken: "BUY", "SELL", "STOP" or None.
        """
        direction  = signal.get("direction", "HOLD")
        strength   = float(signal.get("strength", 0))
        confidence = float(signal.get("confidence", 0))

        open_positions = self._get_positions("open")
        open_symbols   = {p["symbol"] for p in open_positions}

        # ── BUY ──────────────────────────────────────────────────────
        if (direction == "BUY"
                and strength >= BUY_THRESHOLD
                and confidence >= BUY_CONFIDENCE_MIN
                and symbol not in open_symbols):

            portfolio_val = self.get_portfolio_value({symbol: current_price})
            pos_value = portfolio_val * self.position_size_pct
            quantity  = pos_value / current_price

            cost = quantity * current_price * (1 + self.commission)
            cash = self._available_cash()
            if cost > cash:
                logger.info("Paper BUY skipped for %s — insufficient cash (%.0f < %.0f)",
                            symbol, cash, cost)
                return None

            # ATR-based stop-loss; fall back to 5 % fixed
            if atr and atr > 0:
                stop = current_price - STOP_LOSS["atr_multiplier"] * atr
            else:
                stop = current_price * (1 - 0.05)

            self._open_position(symbol, current_price, quantity, stop)
            self._add_trade(symbol, "BUY", current_price, quantity, 0,
                            f"Signal BUY (str={strength:.2f} conf={confidence:.2f})")
            logger.info("Paper BUY  %s @ %.4f  qty=%.4f  stop=%.4f",
                        symbol, current_price, quantity, stop)
            return "BUY"

        # ── SELL ─────────────────────────────────────────────────────
        if direction == "SELL" and symbol in open_symbols:
            pos = next(p for p in open_positions if p["symbol"] == symbol)
            pnl = (current_price - pos["entry_price"]) * pos["quantity"]
            pnl -= pos["quantity"] * current_price * self.commission
            self._close_position(pos["id"], current_price, pnl)
            self._add_trade(symbol, "SELL", current_price, pos["quantity"], pnl,
                            f"Signal SELL (str={strength:.2f})")
            logger.info("Paper SELL %s @ %.4f  pnl=%.2f", symbol, current_price, pnl)
            return "SELL"

        return None

    def update_positions(self, current_prices: dict) -> list[dict]:
        """Check stop-losses and update trailing stops for open positions.

        Args:
            current_prices: {symbol: latest_price}

        Returns:
            List of positions that were stopped out.
        """
        stopped = []
        for pos in self._get_positions("open"):
            sym   = pos["symbol"]
            price = current_prices.get(sym)
            if price is None:
                continue

            # Update trailing stop if price made a new high
            high = pos.get("highest_price") or pos["entry_price"]
            if price > high:
                new_trail = price * (1 - STOP_LOSS["trailing"])
                self._update_position(pos["id"],
                                      highest_price=price,
                                      trailing_stop=new_trail)

            # Evaluate effective stop
            effective_stop = max(
                pos.get("stop_loss")    or 0,
                pos.get("trailing_stop") or 0,
            )
            if effective_stop > 0 and price <= effective_stop:
                pnl = (price - pos["entry_price"]) * pos["quantity"]
                pnl -= pos["quantity"] * price * self.commission
                self._close_position(pos["id"], price, pnl)
                self._add_trade(sym, "STOP", price, pos["quantity"], pnl,
                                f"Stop-loss triggered @ {effective_stop:.4f}")
                stopped.append({**pos, "close_price": price, "pnl": pnl})
                logger.info("Paper STOP %s @ %.4f  stop=%.4f  pnl=%.2f",
                            sym, price, effective_stop, pnl)

        return stopped

    def get_portfolio_summary(self, current_prices: dict | None = None) -> dict:
        """Return a snapshot of the virtual portfolio.

        Args:
            current_prices: Optional {symbol: price} for live P&L.
                            If omitted, entry prices are used.

        Returns:
            dict with keys: initial_capital, total_value, cash, invested,
            unrealized_pnl, realized_pnl, total_return, n_positions, positions.
        """
        current_prices = current_prices or {}
        open_pos = self._get_positions("open")
        all_trades = self._get_trades(500)

        # Cash = initial − cost of all open positions
        invested_cost = sum(p["entry_price"] * p["quantity"] for p in open_pos)
        cash = max(self.initial_capital - invested_cost, 0.0)

        # Unrealized P&L
        unrealized_pnl = 0.0
        invested_value = 0.0
        positions_view = []
        for pos in open_pos:
            price = current_prices.get(pos["symbol"], pos["entry_price"])
            val   = pos["quantity"] * price
            upnl  = (price - pos["entry_price"]) * pos["quantity"]
            invested_value += val
            unrealized_pnl += upnl
            pct = (price / pos["entry_price"] - 1) * 100 if pos["entry_price"] else 0
            stop = max(pos.get("stop_loss") or 0, pos.get("trailing_stop") or 0)
            dist_pct = ((price - stop) / price * 100) if stop and price else None
            positions_view.append({
                "symbol":        pos["symbol"],
                "entry_price":   pos["entry_price"],
                "current_price": price,
                "quantity":      pos["quantity"],
                "unrealized_pnl": round(upnl, 2),
                "pct_change":    round(pct, 2),
                "stop_loss":     round(stop, 4) if stop else None,
                "dist_to_stop_pct": round(dist_pct, 2) if dist_pct is not None else None,
                "opened_at":     pos.get("opened_at", ""),
            })

        # Realized P&L from closed trades
        realized_pnl = sum(
            t["pnl"] for t in all_trades if t["action"] in ("SELL", "STOP")
        )

        total_value  = cash + invested_value
        total_return = (total_value - self.initial_capital) / self.initial_capital

        return {
            "initial_capital": self.initial_capital,
            "total_value":     round(total_value, 2),
            "cash":            round(cash, 2),
            "invested":        round(invested_value, 2),
            "unrealized_pnl":  round(unrealized_pnl, 2),
            "realized_pnl":    round(realized_pnl, 2),
            "total_return":    round(total_return, 4),
            "n_positions":     len(open_pos),
            "positions":       positions_view,
        }

    def reset(self) -> None:
        """Wipe all paper positions and trades (full portfolio reset)."""
        self._reset()
        logger.info("Paper trading portfolio reset to initial capital %.0f",
                    self.initial_capital)

    # ── Internal helpers ──────────────────────────────────────────────

    def get_portfolio_value(self, current_prices: dict | None = None) -> float:
        """Return total portfolio value (cash + invested)."""
        summary = self.get_portfolio_summary(current_prices)
        return summary["total_value"]

    def _available_cash(self) -> float:
        open_pos = self._get_positions("open")
        invested_cost = sum(p["entry_price"] * p["quantity"] for p in open_pos)
        return max(self.initial_capital - invested_cost, 0.0)
