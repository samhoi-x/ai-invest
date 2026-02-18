"""Risk management rules and monitoring."""

import numpy as np
import pandas as pd
from config import RISK, STOP_LOSS
from db.models import add_risk_alert, get_holdings


def check_position_limits(symbol: str, proposed_value: float,
                          portfolio_value: float, asset_type: str = "stock") -> dict:
    """Check if a proposed position violates risk limits.

    Returns dict with 'allowed' (bool), 'violations' (list), 'warnings' (list).
    """
    violations = []
    warnings = []

    position_pct = proposed_value / portfolio_value if portfolio_value > 0 else 1

    # Single position limit
    if position_pct > RISK["max_single_position"]:
        violations.append(
            f"Position {position_pct:.1%} exceeds max {RISK['max_single_position']:.0%}")

    # Crypto allocation limit
    if asset_type == "crypto":
        holdings = get_holdings()
        crypto_value = sum(h["quantity"] * h["avg_cost"] for h in holdings
                          if h.get("asset_type") == "crypto")
        new_crypto_pct = (crypto_value + proposed_value) / portfolio_value
        if new_crypto_pct > RISK["max_crypto_allocation"]:
            violations.append(
                f"Crypto allocation {new_crypto_pct:.1%} exceeds max {RISK['max_crypto_allocation']:.0%}")

    # Trade risk limit
    trade_risk = proposed_value * STOP_LOSS["percentage"]
    trade_risk_pct = trade_risk / portfolio_value
    if trade_risk_pct > RISK["max_trade_risk"]:
        warnings.append(
            f"Trade risk {trade_risk_pct:.2%} exceeds max {RISK['max_trade_risk']:.1%}")

    return {
        "allowed": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
    }


def calculate_stop_loss(entry_price: float, atr_value: float | None = None) -> dict:
    """Calculate stop-loss levels for a position.

    Returns dict with 'atr_stop', 'pct_stop', 'trailing_stop' prices.
    """
    pct_stop = entry_price * (1 - STOP_LOSS["percentage"])
    trailing_stop = entry_price * (1 - STOP_LOSS["trailing"])

    atr_stop = None
    if atr_value is not None and atr_value > 0:
        atr_stop = entry_price - STOP_LOSS["atr_multiplier"] * atr_value

    # Use the tightest stop (most conservative)
    stops = [s for s in [atr_stop, pct_stop, trailing_stop] if s is not None]
    recommended = max(stops) if stops else pct_stop

    return {
        "atr_stop": round(atr_stop, 2) if atr_stop else None,
        "pct_stop": round(pct_stop, 2),
        "trailing_stop": round(trailing_stop, 2),
        "recommended": round(recommended, 2),
    }


def check_drawdown(equity_curve: list[float]) -> dict:
    """Analyze portfolio drawdown and trigger protection rules.

    Returns dict with 'current_drawdown', 'max_drawdown', 'status', 'actions'.
    """
    if not equity_curve or len(equity_curve) < 2:
        return {"current_drawdown": 0, "max_drawdown": 0, "status": "OK", "actions": []}

    peak = equity_curve[0]
    max_dd = 0
    current_dd = 0

    for val in equity_curve:
        if val > peak:
            peak = val
        if peak == 0:
            peak = val
            continue
        dd = (peak - val) / peak
        max_dd = max(max_dd, dd)
        current_dd = dd

    status = "OK"
    actions = []

    if current_dd >= RISK["drawdown_reduce"]:
        status = "CRITICAL"
        actions.append("Reduce positions by 25%")
        actions.append("Move to cash")
        add_risk_alert("drawdown", "critical",
                       f"Drawdown {current_dd:.1%} - Reducing positions", None)
    elif current_dd >= RISK["drawdown_halt"]:
        status = "HALT"
        actions.append("Stop all new BUY signals")
        add_risk_alert("drawdown", "high",
                       f"Drawdown {current_dd:.1%} - Halting new buys", None)
    elif current_dd >= RISK["drawdown_warning"]:
        status = "WARNING"
        actions.append("New position sizes halved")
        add_risk_alert("drawdown", "warning",
                       f"Drawdown {current_dd:.1%} - Reducing position sizes", None)

    return {
        "current_drawdown": round(current_dd, 4),
        "max_drawdown": round(max_dd, 4),
        "status": status,
        "actions": actions,
    }


def check_cash_reserve(cash: float, portfolio_value: float) -> dict:
    """Check if minimum cash reserve is maintained."""
    cash_pct = cash / portfolio_value if portfolio_value > 0 else 1
    ok = cash_pct >= RISK["min_cash_reserve"]

    return {
        "cash": cash,
        "cash_pct": round(cash_pct, 4),
        "min_required": RISK["min_cash_reserve"],
        "ok": ok,
        "message": "" if ok else f"Cash {cash_pct:.1%} below minimum {RISK['min_cash_reserve']:.0%}",
    }


def filter_signal_by_risk(signal: dict, portfolio_value: float,
                          cash: float, equity_curve: list[float]) -> dict:
    """Apply risk filters to a trading signal.

    May downgrade BUY to HOLD if risk limits are breached.
    """
    result = signal.copy()

    # Check drawdown status
    dd = check_drawdown(equity_curve)

    if dd["status"] == "CRITICAL" and signal["direction"] == "BUY":
        result["direction"] = "HOLD"
        result["risk_override"] = "Drawdown critical - BUY blocked"

    elif dd["status"] == "HALT" and signal["direction"] == "BUY":
        result["direction"] = "HOLD"
        result["risk_override"] = "Drawdown halt - No new buys"

    elif dd["status"] == "WARNING" and signal["direction"] == "BUY":
        result["risk_override"] = "Drawdown warning - Position size halved"

    # Check cash reserve
    cash_check = check_cash_reserve(cash, portfolio_value)
    if not cash_check["ok"] and signal["direction"] == "BUY":
        result["direction"] = "HOLD"
        result["risk_override"] = cash_check["message"]

    return result


def compute_portfolio_risk(holdings: list[dict], prices: dict[str, float],
                           returns_data: dict[str, pd.Series]) -> dict:
    """Compute portfolio-level risk metrics.

    Args:
        holdings: List of holding dicts
        prices: Current prices {symbol: price}
        returns_data: Daily returns {symbol: Series}
    """
    if not holdings or not prices:
        return {"var_95": 0, "sharpe": 0, "beta": 0, "correlation_risk": "LOW"}

    values = []
    weights = []
    for h in holdings:
        price = prices.get(h["symbol"], h["avg_cost"])
        val = h["quantity"] * price
        values.append(val)
    total = sum(values) or 1
    weights = [v / total for v in values]

    # Portfolio returns (if we have returns data)
    available = [h["symbol"] for h in holdings if h["symbol"] in returns_data]
    if len(available) >= 2:
        ret_df = pd.DataFrame({s: returns_data[s] for s in available}).dropna()
        if len(ret_df) > 20:
            cov = ret_df.cov() * 252
            port_weights = np.array([weights[i] for i, h in enumerate(holdings)
                                     if h["symbol"] in available])
            if len(port_weights) == len(cov):
                port_var = np.sqrt(port_weights @ cov.values @ port_weights)
                var_95 = port_var * 1.645
                mean_return = ret_df.mean().values @ port_weights * 252
                sharpe = mean_return / port_var if port_var > 0 else 0

                return {
                    "var_95": round(float(var_95), 4),
                    "portfolio_volatility": round(float(port_var), 4),
                    "sharpe": round(float(sharpe), 4),
                    "expected_annual_return": round(float(mean_return), 4),
                }

    return {"var_95": 0, "sharpe": 0, "portfolio_volatility": 0}
