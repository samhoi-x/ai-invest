"""Daily Briefing — assembles and renders a concise market summary.

``get_daily_briefing()`` is cached for 15 minutes so the expensive API
calls are only made once per session refresh cycle.
``render_daily_briefing()`` renders it as a Streamlit sidebar widget.
"""

import logging
import time
from datetime import datetime, date

logger = logging.getLogger(__name__)

_BRIEFING_CACHE: dict = {"data": None, "expires_at": 0.0}
_BRIEFING_TTL = 900  # 15 minutes


def get_daily_briefing() -> dict:
    """Assemble daily briefing data from market signals and DB.

    Returns:
        dict with keys:
          - fear_greed     : {index, label} or None
          - macro_regime   : str
          - breadth_regime : str
          - new_signals    : list of BUY/SELL signal dicts from today
          - position_alerts: list of {symbol, dist_pct} for near-stop positions
          - generated_at   : ISO timestamp string
    """
    now = time.monotonic()
    if _BRIEFING_CACHE["data"] and now < _BRIEFING_CACHE["expires_at"]:
        return _BRIEFING_CACHE["data"]

    briefing: dict = {
        "fear_greed":      None,
        "macro_regime":    "UNKNOWN",
        "breadth_regime":  "NEUTRAL",
        "new_signals":     [],
        "position_alerts": [],
        "generated_at":    datetime.now().isoformat(timespec="seconds"),
    }

    # ── Fear & Greed ─────────────────────────────────────────────────
    try:
        from analysis.fear_greed import get_fear_greed_signal
        fg = get_fear_greed_signal("stock")
        if fg and fg.get("confidence", 0) > 0:
            briefing["fear_greed"] = {
                "index": fg.get("fg_index"),
                "label": fg.get("fg_label", "N/A"),
                "score": fg.get("score", 0.0),
            }
    except Exception as exc:
        logger.debug("Briefing: Fear & Greed unavailable: %s", exc)

    # ── Macro regime ──────────────────────────────────────────────────
    try:
        from analysis.macro_signals import get_macro_signal
        macro = get_macro_signal()
        briefing["macro_regime"] = macro.get("regime", "UNKNOWN")
    except Exception as exc:
        logger.debug("Briefing: Macro signal unavailable: %s", exc)

    # ── Market breadth ────────────────────────────────────────────────
    try:
        from analysis.market_breadth import get_market_breadth
        breadth = get_market_breadth()
        briefing["breadth_regime"] = breadth.get("regime", "NEUTRAL")
    except Exception as exc:
        logger.debug("Briefing: Market breadth unavailable: %s", exc)

    # ── Today's BUY/SELL signals ──────────────────────────────────────
    try:
        from db.models import get_latest_signals
        today_str = str(date.today())
        recent = get_latest_signals(100)
        briefing["new_signals"] = [
            s for s in recent
            if s.get("direction") in ("BUY", "SELL")
            and str(s.get("created_at", ""))[:10] == today_str
        ]
    except Exception as exc:
        logger.debug("Briefing: Signal fetch failed: %s", exc)

    # ── Paper position alerts (near stop-loss) ────────────────────────
    try:
        from db.models import get_paper_positions
        positions = get_paper_positions("open")
        alerts = []
        for pos in positions:
            stop = max(pos.get("stop_loss") or 0, pos.get("trailing_stop") or 0)
            price = pos.get("entry_price", 0)  # best available without live price
            if stop > 0 and price > 0:
                dist_pct = (price - stop) / price * 100
                if dist_pct < 5.0:  # within 5% of stop
                    alerts.append({
                        "symbol":   pos["symbol"],
                        "dist_pct": round(dist_pct, 2),
                        "stop":     round(stop, 4),
                    })
        briefing["position_alerts"] = alerts
    except Exception as exc:
        logger.debug("Briefing: Position alerts unavailable: %s", exc)

    _BRIEFING_CACHE["data"] = briefing
    _BRIEFING_CACHE["expires_at"] = now + _BRIEFING_TTL
    return briefing


def render_daily_briefing(lang: str = "zh") -> None:
    """Render the daily briefing as a Streamlit sidebar section."""
    import streamlit as st

    zh = lang == "zh"
    title = "📋 今日重點" if zh else "📋 Daily Briefing"

    with st.sidebar:
        st.markdown(f"### {title}")
        try:
            b = get_daily_briefing()
        except Exception:
            st.caption("⚠️ 無法載入今日重點" if zh else "⚠️ Briefing unavailable")
            return

        # ── Market Sentiment ─────────────────────────────────────────
        fg = b.get("fear_greed")
        if fg and fg.get("index") is not None:
            idx = fg["index"]
            label = fg["label"]
            if idx <= 25:
                icon, color = "😨", "#e74c3c"
            elif idx <= 45:
                icon, color = "😟", "#e67e22"
            elif idx <= 55:
                icon, color = "😐", "#f1c40f"
            elif idx <= 75:
                icon, color = "😊", "#27ae60"
            else:
                icon, color = "🤑", "#c0392b"
            st.markdown(
                f"**情緒:** {icon} "
                f"<span style='color:{color};font-weight:bold;'>{label} ({idx:.0f})</span>"
                if zh else
                f"**Sentiment:** {icon} "
                f"<span style='color:{color};font-weight:bold;'>{label} ({idx:.0f})</span>",
                unsafe_allow_html=True,
            )

        # ── Macro & Breadth ───────────────────────────────────────────
        _regime_color = {"BULL": "#27ae60", "BEAR": "#e74c3c",
                         "NEUTRAL": "#f1c40f", "UNKNOWN": "#7f8c8d",
                         "HEALTHY": "#27ae60", "WEAK": "#e67e22",
                         "POOR": "#e74c3c"}
        macro = b.get("macro_regime", "UNKNOWN")
        mc    = _regime_color.get(macro, "#7f8c8d")
        breadth = b.get("breadth_regime", "NEUTRAL")
        bc    = _regime_color.get(breadth, "#7f8c8d")

        st.markdown(
            f"**總經:** <span style='color:{mc};font-weight:bold;'>{macro}</span> &nbsp; "
            f"**廣度:** <span style='color:{bc};font-weight:bold;'>{breadth}</span>"
            if zh else
            f"**Macro:** <span style='color:{mc};font-weight:bold;'>{macro}</span> &nbsp; "
            f"**Breadth:** <span style='color:{bc};font-weight:bold;'>{breadth}</span>",
            unsafe_allow_html=True,
        )

        # ── New Signals ───────────────────────────────────────────────
        sigs = b.get("new_signals", [])
        if sigs:
            st.markdown("**今日訊號 🔔**" if zh else "**Today's Signals 🔔**")
            for s in sigs[:5]:  # cap at 5
                icon = "✅" if s["direction"] == "BUY" else "❌"
                st.markdown(
                    f"{icon} **{s['symbol']}** {s['direction']} "
                    f"(信心 {s['confidence']*100:.0f}%)"
                    if zh else
                    f"{icon} **{s['symbol']}** {s['direction']} "
                    f"(conf {s['confidence']*100:.0f}%)"
                )
        else:
            st.caption("今日暫無 BUY/SELL 訊號" if zh else "No BUY/SELL signals today")

        # ── Position Alerts ───────────────────────────────────────────
        alerts = b.get("position_alerts", [])
        if alerts:
            st.markdown("**⚠️ 持倉警示**" if zh else "**⚠️ Position Alerts**")
            for a in alerts:
                st.warning(
                    f"**{a['symbol']}** 距止損僅 {a['dist_pct']:.1f}%"
                    if zh else
                    f"**{a['symbol']}** only {a['dist_pct']:.1f}% from stop-loss"
                )

        ts = b.get("generated_at", "")[:16].replace("T", " ")
        st.caption(f"{'更新' if zh else 'Updated'}: {ts}")
        st.divider()
