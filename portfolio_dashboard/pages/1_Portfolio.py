"""
Page 1 — Portfolio P/L Dashboard
Tracks unrealised gains/losses for all holdings grouped by portfolio.
"""
import sys
from pathlib import Path
# Ensure portfolio_dashboard/ is on the path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from core.data      import load_prices, load_trade_log, load_fx_rates, load_fx_config
from core.analysis  import build_portfolio, portfolio_summary
from core.utils     import style_portfolio_summary
from components.charts  import render_portfolio_view
from components.sidebar import render_data_freshness, render_trade_log_editor, render_currency_selector

st.set_page_config(
    page_title="Portfolio — Investment Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    prices_df, price_file, price_date = load_prices()
    trade_log = load_trade_log()
    fx_rates  = load_fx_rates()
    fx_config = load_fx_config()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        cx = render_currency_selector(fx_rates, currencies_dict=fx_config)
        st.markdown("---")
        render_data_freshness(price_file, price_date)
        st.markdown("---")
        render_trade_log_editor(trade_log)

    # ── Main content ──────────────────────────────────────────────────────────
    st.title("📈 Portfolio Dashboard")
    st.caption(f"Price source: `{price_file or 'None'}`")

    if trade_log.empty:
        st.info("👈 No trades logged yet — add BUY entries in the sidebar.")
        return

    portfolios = sorted(trade_log["portfolio"].dropna().unique().tolist())
    port_all   = build_portfolio(trade_log, prices_df)

    if port_all.empty:
        st.warning("No open positions found — check your trade log data.")
        return

    # ── One tab per portfolio + combined "All" ────────────────────────────────
    tab_labels = ["📊 All Portfolios"] + [f"📁 {p}" for p in portfolios]
    tabs       = st.tabs(tab_labels)

    with tabs[0]:
        if len(portfolios) > 1:
            st.subheader("📂 Portfolio Breakdown")
            summ = portfolio_summary(port_all)
            st.dataframe(
                style_portfolio_summary(summ, cx=cx),
                use_container_width=True, hide_index=True,
                height=50 + 35 * len(summ),
            )
            st.markdown("---")
        render_portfolio_view(
            port_all,
            show_portfolio=len(portfolios) > 1,
            key_suffix="all",
            cx=cx,
        )

    for i, pf in enumerate(portfolios):
        with tabs[i + 1]:
            port_pf = build_portfolio(trade_log, prices_df, portfolio_filter=pf)
            render_portfolio_view(port_pf, show_portfolio=False, key_suffix=f"pf_{i}", cx=cx)


main()
