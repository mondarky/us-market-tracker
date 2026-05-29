"""
Page 2 — Market Data Browser
Browse ticker price history from the latest fetched CSV.
Expandable per-ticker candlestick charts with period stats.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import date

from core.data      import load_prices, build_market_summary, TICKER_PRICE_DIR
from core.utils     import style_market_summary, STALE_THRESHOLD_DAYS
from components.charts  import render_ticker_chart
from components.sidebar import render_data_freshness

st.set_page_config(
    page_title="Market Data — Investment Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    prices_df, price_file, price_date = load_prices()

    with st.sidebar:
        render_data_freshness(price_file, price_date)

    st.header("📊 Market Data")

    if prices_df is None:
        st.error(
            "No price CSV found in `data/ticker_price/`.  "
            "Run `fetch_tickers.py` first."
        )
        return

    # ── File info banner ──────────────────────────────────────────────────────
    ticker_count = prices_df["Ticker"].nunique()
    if price_date:
        gap       = (date.today() - price_date).days
        freshness = "✅ Fresh" if gap <= STALE_THRESHOLD_DAYS else f"⚠️ Stale ({gap}d old)"
        st.caption(
            f"Source: `{price_file}` — **{ticker_count} tickers** — {freshness}"
        )

    summary = build_market_summary(prices_df)
    if summary.empty:
        st.warning("Could not build summary — check the price CSV format.")
        return

    # ── Summary table ─────────────────────────────────────────────────────────
    st.subheader("📋 Ticker Summary")
    st.caption(
        "Click any column header to sort.  "
        "🟢 OK · 🟠 STALE/SHORT · 🔴 ERROR"
    )
    display_cols = [c for c in
                    ["Ticker", "Status", "Trading Days", "Date Range",
                     "Latest Close", "Period High", "Period Low"]
                    if c in summary.columns]
    st.dataframe(
        style_market_summary(summary[display_cols]),
        use_container_width=True, hide_index=True,
        height=min(80 + 35 * len(summary), 600),
    )

    st.markdown("---")

    # ── Per-ticker expandable candlestick charts ───────────────────────────────
    st.subheader("📈 Ticker Charts")
    st.caption("Expand a ticker to view its candlestick price history.")

    has_data = summary[summary["_has_data"]]
    no_data  = summary[~summary["_has_data"]]

    for _, row in has_data.iterrows():
        ticker = row["Ticker"]
        ok_df  = prices_df[
            (prices_df["Ticker"] == ticker)
            & prices_df["fetch_status"].str.startswith("OK", na=False)
        ].dropna(subset=["Date"]).sort_values("Date").copy()

        if ok_df.empty:
            continue

        label = (
            f"{ticker}   "
            f"Close ${row['Latest Close']:,.2f}  ·  "
            f"High ${row['Period High']:,.2f}  ·  "
            f"Low ${row['Period Low']:,.2f}  ·  "
            f"{row['Date Range']}  ({row['Trading Days']} days)"
        )
        with st.expander(label, expanded=False):
            render_ticker_chart(ok_df, ticker, key_suffix=ticker)

    if not no_data.empty:
        with st.expander(
            f"❌ {len(no_data)} ticker(s) with no data / ERROR", expanded=False
        ):
            for _, row in no_data.iterrows():
                st.write(f"**{row['Ticker']}** — `{row['Status']}`")


main()
