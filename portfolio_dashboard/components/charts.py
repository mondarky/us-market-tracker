"""
Chart-building components — Streamlit + Plotly rendering only.
No data I/O, no business logic.
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from core.utils import PALETTE, style_holdings_table


# ── Helpers ───────────────────────────────────────────────────────────────────

def portfolio_color_map(port) -> dict[str, str]:
    """Assign a stable palette colour to each portfolio (alphabetical order)."""
    pfs = sorted(port["Portfolio"].dropna().unique().tolist())
    return {pf: PALETTE[i % len(PALETTE)] for i, pf in enumerate(pfs)}


# ── Market data chart ─────────────────────────────────────────────────────────

def render_ticker_chart(ok_df, ticker: str, key_suffix: str) -> None:
    """
    4-metric stats row + candlestick chart for a single ticker.
    key_suffix must be unique per ticker to avoid Streamlit element-ID collisions.
    """
    latest  = float(ok_df["Close"].iloc[-1])
    p_high  = float(ok_df["High"].max()) if "High" in ok_df.columns else float(ok_df["Close"].max())
    p_low   = float(ok_df["Low"].min())  if "Low"  in ok_df.columns else float(ok_df["Close"].min())
    rng     = p_high - p_low
    rng_pct = rng / p_low * 100 if p_low > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Latest Close", f"${latest:,.2f}")
    m2.metric("Period High",  f"${p_high:,.2f}")
    m3.metric("Period Low",   f"${p_low:,.2f}")
    m4.metric("Period Range", f"${rng:,.2f}", f"{rng_pct:.1f}%")

    fig = go.Figure(go.Candlestick(
        x=ok_df["Date"],
        open=ok_df["Open"]  if "Open"  in ok_df.columns else ok_df["Close"],
        high=ok_df["High"]  if "High"  in ok_df.columns else ok_df["Close"],
        low=ok_df["Low"]    if "Low"   in ok_df.columns else ok_df["Close"],
        close=ok_df["Close"],
        name=ticker,
        increasing_line_color="#27ae60",
        decreasing_line_color="#e74c3c",
        hovertext=ok_df["Date"].dt.strftime("%d %b %y"),
    ))
    fig.update_layout(
        xaxis_title=None,
        yaxis_title="Price ($)",
        yaxis=dict(tickprefix="$", tickformat=",.2f"),
        xaxis_rangeslider_visible=False,
        margin=dict(t=30, b=20, l=10, r=90),
        height=380,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"chart_{key_suffix}")


# ── Portfolio view ────────────────────────────────────────────────────────────

def render_portfolio_view(port, show_portfolio: bool, key_suffix: str) -> None:
    """
    Render the full portfolio view for one tab:
      4 metric cards → sortable holdings table → allocation pie + P/L bars.

    show_portfolio=True   → show Portfolio column; colour bars by portfolio
    show_portfolio=False  → hide Portfolio column; colour P/L bars green/red
    key_suffix            → unique string per tab (e.g. "all", "pf_0")
    """
    if port.empty:
        st.info("No holdings to display.")
        return

    priced    = port[port["_has_price"]]
    no_price  = port[~port["_has_price"]]
    cost_all  = port["Cost Basis"].sum()
    cost_prcd = priced["Cost Basis"].sum()
    total_mkt = priced["Market Value"].sum() if not priced.empty else None
    total_pl_d = (total_mkt - cost_prcd) if total_mkt is not None else None
    total_pl_p = (total_pl_d / cost_prcd * 100
                  if (total_pl_d is not None and cost_prcd > 0) else None)

    # ── Metric cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Cost Basis",   f"${cost_all:,.2f}",   help="Shares × avg cost")
    c2.metric("📊 Market Value",
              f"${total_mkt:,.2f}"   if total_mkt  is not None else "N/A",
              help="Priced positions only")
    c3.metric("📈 P/L $",
              f"${total_pl_d:+,.2f}" if total_pl_d is not None else "N/A",
              delta=f"{total_pl_d:+,.2f}" if total_pl_d is not None else None)
    c4.metric("📉 P/L %",
              f"{total_pl_p:+.2f}%"  if total_pl_p is not None else "N/A",
              delta=f"{total_pl_p:+.2f}%" if total_pl_p is not None else None)

    if not no_price.empty:
        st.warning(f"⚠️ No price data for: **{', '.join(no_price['Ticker'].tolist())}**.")

    st.markdown("---")

    # ── Holdings table ────────────────────────────────────────────────────────
    st.subheader("📋 Holdings")
    sort_opts = (["Portfolio", "Ticker"] if show_portfolio else ["Ticker"]) + \
                ["Market Value", "P/L $", "P/L %", "Cost Basis", "Shares"]
    sc, sd = st.columns([2, 1])
    with sc:
        sort_by = st.selectbox("Sort by", sort_opts, index=0,
                               label_visibility="collapsed", key=f"sort_{key_suffix}")
    with sd:
        asc = st.toggle("Ascending", value=True, key=f"asc_{key_suffix}")

    display_port = port.sort_values(sort_by, ascending=asc, na_position="last")
    st.dataframe(
        style_holdings_table(display_port, show_portfolio=show_portfolio),
        use_container_width=True, hide_index=True,
        height=min(max(80 + 35 * len(display_port), 150), 650),
    )

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────────────────────────
    chart_data = port.dropna(subset=["Market Value"])
    if chart_data.empty:
        st.info("Charts require price data — run `fetch_tickers.py` first.")
        return

    color_map = portfolio_color_map(port) if show_portfolio else {}

    col_l, col_r = st.columns(2)

    # Allocation pie
    with col_l:
        st.subheader("🥧 Allocation")
        if show_portfolio:
            r1, r2 = st.columns(2)
            with r1:
                alloc_by  = st.radio("Basis", ["Market Value", "Cost Basis"],
                                     horizontal=False, key=f"alloc_basis_{key_suffix}")
            with r2:
                group_dim = st.radio("Group by", ["Ticker", "Portfolio"],
                                     horizontal=False, key=f"alloc_grp_{key_suffix}")
        else:
            alloc_by  = st.radio("Basis", ["Market Value", "Cost Basis"],
                                 horizontal=True, key=f"alloc_basis_{key_suffix}")
            group_dim = "Ticker"

        pie_src = chart_data if alloc_by == "Market Value" else port
        if group_dim == "Portfolio":
            pie_df    = pie_src.groupby("Portfolio", as_index=False).agg({alloc_by: "sum"})
            names_col = "Portfolio"
        else:
            pie_df    = pie_src
            names_col = "Ticker"

        fig_pie = px.pie(pie_df, values=alloc_by, names=names_col,
                         hole=0.42, color_discrete_sequence=PALETTE)
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10),
                               height=380, showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True, key=f"pie_{key_suffix}")

    # P/L $ bar
    with col_r:
        st.subheader("💵 P/L $ per Ticker")
        bar_data   = port.dropna(subset=["P/L $"]).sort_values("P/L $")
        bar_colors = (
            [color_map.get(pf, "#888") for pf in bar_data["Portfolio"]]
            if show_portfolio
            else ["#27ae60" if v >= 0 else "#e74c3c" for v in bar_data["P/L $"]]
        )
        fig_bar = go.Figure(go.Bar(
            x=bar_data["Ticker"], y=bar_data["P/L $"],
            marker_color=bar_colors,
            text=[f"${v:+,.2f}" for v in bar_data["P/L $"]],
            textposition="outside", textfont=dict(size=10),
        ))
        fig_bar.update_layout(
            xaxis_title=None, yaxis_title="Unrealised P/L ($)",
            yaxis=dict(zeroline=True, zerolinewidth=1.5, zerolinecolor="#aaa"),
            margin=dict(t=10, b=20, l=20, r=20), height=380,
        )
        st.plotly_chart(fig_bar, use_container_width=True, key=f"bar_{key_suffix}")

    # P/L % bar (full width)
    st.subheader("📊 P/L % per Ticker")
    pct_data   = port.dropna(subset=["P/L %"]).sort_values("P/L %")
    pct_colors = (
        [color_map.get(pf, "#888") for pf in pct_data["Portfolio"]]
        if show_portfolio
        else ["#27ae60" if v >= 0 else "#e74c3c" for v in pct_data["P/L %"]]
    )
    fig_pct = go.Figure(go.Bar(
        x=pct_data["Ticker"], y=pct_data["P/L %"],
        marker_color=pct_colors,
        text=[f"{v:+.1f}%" for v in pct_data["P/L %"]],
        textposition="outside", textfont=dict(size=10),
    ))
    fig_pct.update_layout(
        xaxis_title=None, yaxis_title="Unrealised P/L (%)",
        yaxis=dict(zeroline=True, zerolinewidth=1.5, zerolinecolor="#aaa"),
        margin=dict(t=10, b=20, l=20, r=50), height=350,
    )
    st.plotly_chart(fig_pct, use_container_width=True, key=f"pct_{key_suffix}")
