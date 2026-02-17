"""Plotly chart components for the dashboard."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def candlestick_chart(df: pd.DataFrame, symbol: str, indicators: dict | None = None,
                      height: int = 600) -> go.Figure:
    """Create an interactive candlestick chart with optional indicator overlays.

    Args:
        df: OHLCV DataFrame
        symbol: Asset symbol for title
        indicators: Dict of indicator name → Series to overlay
        height: Chart height in pixels
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
        subplot_titles=[f"{symbol} Price", "Volume"],
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="OHLC",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    # Overlay indicators
    if indicators:
        colors = ["#FF9800", "#2196F3", "#9C27B0", "#4CAF50", "#F44336", "#00BCD4"]
        for i, (name, series) in enumerate(indicators.items()):
            if series is not None and not series.empty:
                color = colors[i % len(colors)]
                if name.startswith("BB_"):
                    dash = "dash" if "upper" in name or "lower" in name else "solid"
                    fig.add_trace(go.Scatter(
                        x=series.index, y=series, name=name,
                        line=dict(color=color, width=1, dash=dash), opacity=0.7,
                    ), row=1, col=1)
                else:
                    fig.add_trace(go.Scatter(
                        x=series.index, y=series, name=name,
                        line=dict(color=color, width=1.5),
                    ), row=1, col=1)

    # Volume bars
    if "volume" in df.columns:
        colors_vol = ["#26a69a" if c >= o else "#ef5350"
                      for o, c in zip(df["open"], df["close"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="Volume",
            marker_color=colors_vol, opacity=0.5,
        ), row=2, col=1)

    fig.update_layout(
        height=height, xaxis_rangeslider_visible=False,
        template="plotly_dark", margin=dict(l=50, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def line_chart(series_dict: dict, title: str = "", height: int = 400,
               y_title: str = "") -> go.Figure:
    """Create a multi-line chart from a dict of name→Series."""
    fig = go.Figure()
    colors = ["#2196F3", "#FF9800", "#4CAF50", "#F44336", "#9C27B0", "#00BCD4"]
    for i, (name, series) in enumerate(series_dict.items()):
        if series is not None:
            fig.add_trace(go.Scatter(
                x=series.index, y=series, name=name,
                line=dict(color=colors[i % len(colors)], width=2),
            ))
    fig.update_layout(
        title=title, height=height, template="plotly_dark",
        yaxis_title=y_title,
        margin=dict(l=50, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def pie_chart(labels: list, values: list, title: str = "",
              height: int = 400) -> go.Figure:
    """Create a pie/donut chart for allocations."""
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.4,
        textinfo="label+percent", textposition="outside",
    ))
    fig.update_layout(
        title=title, height=height, template="plotly_dark",
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def bar_chart(x, y, title: str = "", color: str = "#2196F3",
              height: int = 400) -> go.Figure:
    """Create a bar chart."""
    colors = [("#26a69a" if v >= 0 else "#ef5350") for v in y]
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=colors))
    fig.update_layout(
        title=title, height=height, template="plotly_dark",
        margin=dict(l=50, r=20, t=40, b=20),
    )
    return fig


def heatmap_chart(df: pd.DataFrame, title: str = "",
                  height: int = 400) -> go.Figure:
    """Create a heatmap (e.g., for correlation or returns)."""
    fig = go.Figure(go.Heatmap(
        z=df.values, x=df.columns, y=df.index,
        colorscale="RdYlGn", zmid=0,
        text=df.round(2).values, texttemplate="%{text}",
    ))
    fig.update_layout(
        title=title, height=height, template="plotly_dark",
        margin=dict(l=80, r=20, t=40, b=20),
    )
    return fig
