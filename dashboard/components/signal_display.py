"""Signal display components."""

import streamlit as st
import pandas as pd
from i18n import t


def signal_table(signals: list[dict]):
    """Display a table of trading signals."""
    if not signals:
        st.caption("No signals available.")
        return
    df = pd.DataFrame(signals)
    display_cols = ["symbol", "direction", "strength", "confidence",
                    "technical_score", "sentiment_score", "ml_score", "created_at"]
    available = [c for c in display_cols if c in df.columns]
    df = df[available]

    def color_direction(val):
        if val == "BUY":
            return "color: #26a69a; font-weight: bold"
        elif val == "SELL":
            return "color: #ef5350; font-weight: bold"
        return "color: #FFC107"

    if "direction" in df.columns:
        styled = df.style.map(color_direction, subset=["direction"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def factor_breakdown(tech: float, sent: float, ml: float):
    """Show a horizontal breakdown of the three factors with educational tooltips."""
    cols = st.columns(3)
    with cols[0]:
        st.metric("Technical", f"{tech:+.2f}", help=t("tip_technical"))
        st.progress(max(0, min(1, (tech + 1) / 2)))
    with cols[1]:
        st.metric("Sentiment", f"{sent:+.2f}", help=t("tip_sentiment"))
        st.progress(max(0, min(1, (sent + 1) / 2)))
    with cols[2]:
        st.metric("ML Model", f"{ml:+.2f}", help=t("tip_ml"))
        st.progress(max(0, min(1, (ml + 1) / 2)))


def signal_explanation_panel(explanations: dict):
    """Display a beginner-friendly explanation of the signal.

    Args:
        explanations: Output of signal_explainer.explain_signal().
    """
    # Direction reason
    st.markdown(f"**{explanations.get('direction_reason', '')}**")

    # Factor explanations
    for item in explanations.get("factor_explanations", []):
        st.markdown(f"- {item}")

    st.markdown("---")

    # Indicator explanations
    st.markdown(f"**{t('tech_details')}**")
    for item in explanations.get("indicator_explanations", []):
        st.markdown(f"- {item}")

    st.markdown("---")

    # Risk and confidence
    risk_text = explanations.get("risk_explanation", "")
    conf_text = explanations.get("confidence_explanation", "")
    st.info(f"{risk_text}\n\n{conf_text}")


def action_plan_panel(action_plan: dict, lang: str = "en"):
    """Display a concrete action plan card.

    Args:
        action_plan: Output of risk_manager.generate_action_plan().
        lang: "en" or "zh".
    """
    action = action_plan.get("action", "HOLD")

    # Blocked by risk filter
    if action_plan.get("blocked"):
        st.error(f"🚫 **{t('trade_blocked')}**: {action_plan.get('blocked_reason', '')}")
        return

    # HOLD — nothing actionable
    if action == "HOLD":
        st.info(f"⏸️ **HOLD** — {t('action_plan')}")
        return

    # Warnings
    for w in action_plan.get("warnings", []):
        st.warning(f"⚠️ {w}")

    # Colour scheme
    if action == "BUY":
        border_color = "#26a69a"
        bg_color = "rgba(38,166,154,0.08)"
        action_label = "BUY" if lang == "en" else "買入"
    else:
        border_color = "#ef5350"
        bg_color = "rgba(239,83,80,0.08)"
        action_label = "SELL" if lang == "en" else "賣出"

    shares = action_plan.get("shares", 0)
    entry = action_plan.get("entry_price", 0)
    stop = action_plan.get("stop_loss", 0)
    stop_pct = action_plan.get("stop_loss_pct", 0)
    pos_value = action_plan.get("position_value", 0)
    pos_pct = action_plan.get("position_pct", 0)
    total_risk = action_plan.get("total_risk", 0)
    risk_pct = action_plan.get("risk_pct", 0)
    target = action_plan.get("target_price")
    rr = action_plan.get("risk_reward", "N/A")
    kelly_frac = action_plan.get("kelly_fraction")

    kelly_html = ""
    if kelly_frac is not None:
        kelly_html = (
            f"<tr><td style='padding:4px 12px;color:#90A4AE;'>Kelly Fraction</td>"
            f"<td style='padding:4px 12px;'><b>{kelly_frac:.1%}</b> "
            f"<span style='color:#90A4AE;font-size:0.85em;'>(half-Kelly)</span></td></tr>"
        )

    target_html = ""
    if target is not None:
        target_label = t("target_price")
        rr_label = t("risk_reward")
        target_html = f"""
        <tr><td style="padding:4px 12px;color:#90A4AE;">{target_label}</td>
            <td style="padding:4px 12px;"><b>${target:,.2f}</b></td></tr>
        <tr><td style="padding:4px 12px;color:#90A4AE;">{rr_label}</td>
            <td style="padding:4px 12px;"><b>{rr}</b></td></tr>
        """

    html = f"""
    <div style="padding:16px; border-radius:12px; border:2px solid {border_color};
                background:{bg_color}; margin-bottom:12px;">
        <h3 style="margin:0 0 8px 0;">{t('action_plan')}: {action_label} {shares} shares @ ~${entry:,.2f}</h3>
        <table style="width:100%; border-collapse:collapse;">
        <tr><td style="padding:4px 12px;color:#90A4AE;">{t('entry_price')}</td>
            <td style="padding:4px 12px;"><b>${entry:,.2f}</b></td></tr>
        <tr><td style="padding:4px 12px;color:#90A4AE;">{t('stop_loss_price')}</td>
            <td style="padding:4px 12px;"><b>${stop:,.2f}</b> ({stop_pct:.1%} {t('below_entry')})</td></tr>
        <tr><td style="padding:4px 12px;color:#90A4AE;">{t('position_size')}</td>
            <td style="padding:4px 12px;"><b>${pos_value:,.2f}</b> ({pos_pct:.1%} {t('of_portfolio')})</td></tr>
        <tr><td style="padding:4px 12px;color:#90A4AE;">{t('dollar_risk')}</td>
            <td style="padding:4px 12px;"><b>${total_risk:,.2f}</b> ({risk_pct:.2%} {t('of_portfolio')})</td></tr>
        {kelly_html}
        {target_html}
        </table>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
