"""Risk management rules and monitoring."""

import numpy as np
import pandas as pd
from config import RISK, STOP_LOSS
from db.models import add_risk_alert, get_holdings


def check_position_limits(symbol: str, proposed_value: float,
                          portfolio_value: float, asset_type: str = "stock",
                          current_crypto_value: float | None = None) -> dict:
    """Check if a proposed position violates risk limits.

    Args:
        current_crypto_value: Sum of current market values of all existing crypto
            holdings.  When provided, used instead of cost-basis from the DB so that
            the crypto allocation check reflects real exposure rather than historical
            cost (which under-reports exposure for appreciated positions).

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
        if current_crypto_value is not None:
            crypto_value = current_crypto_value
        else:
            # Fallback: use cost basis from DB (conservative for losing positions,
            # but may understate exposure for appreciated holdings)
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


def generate_action_plan(
    symbol: str,
    signal: dict,
    current_price: float,
    atr_value: float | None,
    portfolio_value: float,
    cash: float,
    asset_type: str = "stock",
    equity_curve: list[float] | None = None,
) -> dict:
    """Generate a concrete, beginner-friendly action plan from a combined signal.

    Reuses existing risk-management helpers to compute stop-loss, position
    sizing, and risk limits.  Returns a dict that UI components can display
    directly.
    """
    direction = signal.get("direction", "HOLD")

    # Default empty plan for HOLD
    if direction == "HOLD":
        return {
            "action": "HOLD",
            "shares": 0,
            "entry_price": current_price,
            "position_value": 0,
            "position_pct": 0,
            "stop_loss": 0,
            "stop_loss_pct": 0,
            "total_risk": 0,
            "risk_pct": 0,
            "target_price": None,
            "risk_reward": "N/A",
            "warnings": [],
            "blocked": False,
            "blocked_reason": None,
        }

    # 1. Risk filter — may downgrade BUY → HOLD or attach warnings
    filtered = filter_signal_by_risk(signal, portfolio_value, cash, equity_curve or [])
    warnings: list[str] = []
    blocked = False
    blocked_reason = None

    if filtered["direction"] != direction:
        blocked = True
        blocked_reason = filtered.get("risk_override", "Blocked by risk filter")
        return {
            "action": direction,
            "shares": 0,
            "entry_price": current_price,
            "position_value": 0,
            "position_pct": 0,
            "stop_loss": 0,
            "stop_loss_pct": 0,
            "total_risk": 0,
            "risk_pct": 0,
            "target_price": None,
            "risk_reward": "N/A",
            "warnings": [],
            "blocked": blocked,
            "blocked_reason": blocked_reason,
        }

    if filtered.get("risk_override"):
        warnings.append(filtered["risk_override"])

    # 2. Stop-loss
    stop_info = calculate_stop_loss(current_price, atr_value)
    stop_price = stop_info["recommended"]
    stop_distance = abs(current_price - stop_price)
    stop_pct = stop_distance / current_price if current_price > 0 else STOP_LOSS["percentage"]

    # 3. Position sizing — risk-based
    if stop_pct > 0:
        risk_budget = RISK["max_trade_risk"] * portfolio_value  # e.g. 1% of portfolio
        position_value = risk_budget / stop_pct
    else:
        position_value = RISK["max_trade_risk"] * portfolio_value

    # Cap by max single position and available cash
    max_position = RISK["max_single_position"] * portfolio_value
    position_value = min(position_value, max_position, cash * 0.9)
    position_value = max(position_value, 0)

    # 4. Check position limits
    limits = check_position_limits(symbol, position_value, portfolio_value, asset_type)
    if not limits["allowed"]:
        warnings.extend(limits["violations"])
        # Reduce to max allowed
        position_value = min(position_value, RISK["max_single_position"] * portfolio_value)
    warnings.extend(limits.get("warnings", []))

    # 5. Shares / units
    if asset_type == "crypto":
        shares = round(position_value / current_price, 4) if current_price > 0 else 0
    else:
        shares = int(position_value / current_price) if current_price > 0 else 0

    actual_position_value = shares * current_price
    position_pct = actual_position_value / portfolio_value if portfolio_value > 0 else 0

    # 6. Dollar risk
    total_risk = shares * stop_distance
    risk_pct = total_risk / portfolio_value if portfolio_value > 0 else 0

    # 7. Target price (2:1 risk-reward)
    if direction == "BUY":
        target_price = round(current_price + 2 * stop_distance, 2)
    elif direction == "SELL":
        target_price = round(current_price - 2 * stop_distance, 2)
    else:
        target_price = None

    risk_reward = "1:2"

    return {
        "action": direction,
        "shares": shares,
        "entry_price": round(current_price, 2),
        "position_value": round(actual_position_value, 2),
        "position_pct": round(position_pct, 4),
        "stop_loss": stop_price,
        "stop_loss_pct": round(stop_pct, 4),
        "total_risk": round(total_risk, 2),
        "risk_pct": round(risk_pct, 4),
        "target_price": target_price,
        "risk_reward": risk_reward,
        "warnings": warnings,
        "blocked": blocked,
        "blocked_reason": blocked_reason,
    }
