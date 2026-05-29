"""
Page 3 — Performance
Portfolio value over time, running P/L curve, and best/worst week callouts.

History depth grows automatically as more ticker CSVs accumulate in
data/ticker_price/ — run fetch_tickers.py regularly to extend the chart.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from core.data      import load_prices, load_trade_log, load_performance_series, load_fx_rates, load_fx_config
from core.analysis  import get_weekly_performance
from components.charts  import render_performance_charts
from components.sidebar import render_data_freshness, render_currency_selector

st.set_page_config(
    page_title="Performance — Investment Dashboard",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    prices_df, price_file, price_date = load_prices()
    trade_log = load_trade_log()
    fx_rates  = load_fx_rates()
    fx_config = load_fx_config()

    with st.sidebar:
        cx = render_currency_selector(fx_rates, currencies_dict=fx_config)
        st.markdown("---")
        render_data_freshness(price_file, price_date)
        if prices_df is not None:
            n_days = prices_df["Date"].dropna().nunique()
            st.caption(f"Price history: **{n_days} trading day(s)** in current data")

    st.title("📉 Performance")
    st.caption(
        f"Price source: `{price_file or 'None'}`  •  "
        "History grows as more fetches accumulate in `data/ticker_price/`"
    )

    if trade_log.empty:
        st.info("👈 No trades logged — add BUY entries in the Portfolio page sidebar.")
        return

    if prices_df is None:
        st.error("No price data found. Run `fetch_tickers.py` first.")
        return

    portfolios = sorted(trade_log["portfolio"].dropna().unique().tolist())

    # ── Tabs: All + per portfolio ─────────────────────────────────────────────
    tab_labels = ["📊 All Portfolios"] + [f"📁 {p}" for p in portfolios]
    tabs       = st.tabs(tab_labels)

    with tabs[0]:
        series = load_performance_series(trade_log, prices_df, portfolio=None)
        weekly = get_weekly_performance(series)
        render_performance_charts(series, weekly, key_suffix="all", cx=cx)

    for i, pf in enumerate(portfolios):
        with tabs[i + 1]:
            series = load_performance_series(trade_log, prices_df, portfolio=pf)
            weekly = get_weekly_performance(series)
            render_performance_charts(series, weekly, key_suffix=f"pf_{i}", cx=cx)


main()
