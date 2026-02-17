"""Notification system: Telegram and Email alerts for trading signals."""

import logging
import requests
from datetime import datetime
from config import PAGE_TITLE

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  Telegram Notifier
# ══════════════════════════════════════════════════════════════════════

def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """Send a message via Telegram Bot API.

    Args:
        bot_token: Telegram bot token from @BotFather
        chat_id: Target chat/group/channel ID
        message: Message text (supports MarkdownV2)

    Returns:
        True if sent successfully.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured (missing token or chat_id)")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


def format_signal_message(symbol: str, signal: dict) -> str:
    """Format a trading signal into a readable Telegram message."""
    direction = signal.get("direction", "HOLD")
    icon = {"BUY": "\u2705", "SELL": "\u274c", "HOLD": "\u23f8\ufe0f"}.get(direction, "\u2753")

    strength = signal.get("strength", 0)
    confidence = signal.get("confidence", 0)
    tech = signal.get("technical_score", 0)
    sent = signal.get("sentiment_score", 0)
    ml = signal.get("ml_score", 0)
    risk = signal.get("risk_level", "N/A")

    msg = (
        f"{icon} <b>{PAGE_TITLE}</b>\n"
        f"\n"
        f"<b>{symbol} — {direction}</b>\n"
        f"Strength: <code>{strength:+.3f}</code>\n"
        f"Confidence: <code>{confidence:.0%}</code>\n"
        f"Risk Level: <code>{risk}</code>\n"
        f"\n"
        f"<b>Factor Scores:</b>\n"
        f"  Technical: <code>{tech:+.3f}</code>\n"
        f"  Sentiment: <code>{sent:+.3f}</code>\n"
        f"  ML Model:  <code>{ml:+.3f}</code>\n"
        f"\n"
        f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>"
    )
    return msg


def format_risk_alert_message(alert_type: str, severity: str, message: str,
                               symbol: str = None) -> str:
    """Format a risk alert into a Telegram message."""
    sev_icon = {"critical": "\U0001f534", "high": "\U0001f7e0",
                "warning": "\U0001f7e1", "info": "\U0001f535"}.get(severity, "\u26aa")
    sym_str = f" ({symbol})" if symbol else ""
    return (
        f"{sev_icon} <b>Risk Alert{sym_str}</b>\n"
        f"Type: <code>{alert_type}</code>\n"
        f"Severity: <code>{severity.upper()}</code>\n"
        f"Message: {message}\n"
        f"\n"
        f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>"
    )


def format_daily_summary(signals: list[dict]) -> str:
    """Format a daily signal summary message."""
    if not signals:
        return f"\U0001f4ca <b>{PAGE_TITLE} - Daily Summary</b>\n\nNo signals generated today."

    buys = [s for s in signals if s.get("direction") == "BUY"]
    sells = [s for s in signals if s.get("direction") == "SELL"]
    holds = [s for s in signals if s.get("direction") == "HOLD"]

    lines = [
        f"\U0001f4ca <b>{PAGE_TITLE} - Daily Summary</b>",
        f"\U0001f4c5 {datetime.now().strftime('%Y-%m-%d')}",
        f"",
        f"Total signals: {len(signals)}",
        f"\u2705 BUY: {len(buys)}  |  \u274c SELL: {len(sells)}  |  \u23f8\ufe0f HOLD: {len(holds)}",
        f"",
    ]

    if buys:
        lines.append("<b>BUY Signals:</b>")
        for s in buys[:5]:
            lines.append(f"  \u2022 {s['symbol']} (confidence: {s.get('confidence', 0):.0%})")

    if sells:
        lines.append("<b>SELL Signals:</b>")
        for s in sells[:5]:
            lines.append(f"  \u2022 {s['symbol']} (confidence: {s.get('confidence', 0):.0%})")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
#  Unified notify interface
# ══════════════════════════════════════════════════════════════════════

def notify_signal(symbol: str, signal: dict, bot_token: str = "", chat_id: str = ""):
    """Send signal notification via all configured channels."""
    if not bot_token or not chat_id:
        try:
            from db.models import get_setting
            bot_token = bot_token or get_setting("telegram_bot_token", "")
            chat_id = chat_id or get_setting("telegram_chat_id", "")
        except Exception:
            pass

    if bot_token and chat_id:
        msg = format_signal_message(symbol, signal)
        send_telegram(bot_token, chat_id, msg)


def notify_risk_alert(alert_type: str, severity: str, message: str,
                       symbol: str = None):
    """Send risk alert via all configured channels."""
    try:
        from db.models import get_setting
        bot_token = get_setting("telegram_bot_token", "")
        chat_id = get_setting("telegram_chat_id", "")
    except Exception:
        return

    if bot_token and chat_id:
        msg = format_risk_alert_message(alert_type, severity, message, symbol)
        send_telegram(bot_token, chat_id, msg)


def notify_daily_summary(signals: list[dict]):
    """Send daily summary via all configured channels."""
    try:
        from db.models import get_setting
        bot_token = get_setting("telegram_bot_token", "")
        chat_id = get_setting("telegram_chat_id", "")
    except Exception:
        return

    if bot_token and chat_id:
        msg = format_daily_summary(signals)
        send_telegram(bot_token, chat_id, msg)
