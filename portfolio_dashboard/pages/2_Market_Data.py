"""
Page 2 — Market Data Browser
Browse ticker price history from the latest fetched CSV.
Expandable per-ticker candlestick charts with search + sort controls.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import date

from core.data      import load_prices, build_market_summary
from core.utils     import STALE_THRESHOLD_DAYS
from components.charts  import render_ticker_chart
from components.sidebar import render_data_freshness

st.set_page_config(
    page_title="Market Data — Investment Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sort column mapping: display label → DataFrame column
_SORT_OPTIONS = {
    "Ticker A → Z":            ("Ticker",        True),
    "Ticker Z → A":            ("Ticker",        False),
    "Latest Close ↑ (cheap)":  ("Latest Close",  True),
    "Latest Close ↓ (pricey)": ("Latest Close",  False),
    "Period High ↓":           ("Period High",   False),
    "Period High ↑":           ("Period High",   True),
    "Period Low ↓":            ("Period Low",    False),
    "Period Low ↑":            ("Period Low",    True),
    "Period Range % ↓":        ("_range_pct",    False),
    "Period Range % ↑":        ("_range_pct",    True),
    "Trading Days ↓ (most)":   ("Trading Days",  False),
    "Trading Days ↑ (least)":  ("Trading Days",  True),
}


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

    has_data = summary[summary["_has_data"]].copy()
    no_data  = summary[~summary["_has_data"]]

    # Pre-compute period range % for sorting
    has_data["_range_pct"] = (
        (has_data["Period High"] - has_data["Period Low"])
        / has_data["Period Low"] * 100
    ).round(2)

    # ── Search + Sort controls ────────────────────────────────────────────────
    st.subheader("📈 Ticker Charts")

    col_search, col_sort = st.columns([1, 2])
    with col_search:
        search = st.text_input(
            "Search",
            placeholder="Type a symbol, e.g. NLR …",
            label_visibility="collapsed",
        )
    with col_sort:
        sort_label = st.selectbox(
            "Sort",
            options=list(_SORT_OPTIONS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    # Apply search filter
    if search.strip():
        has_data = has_data[
            has_data["Ticker"].str.contains(search.strip(), case=False, na=False)
        ]

    # Apply sort
    sort_col, sort_asc = _SORT_OPTIONS[sort_label]
    has_data = has_data.sort_values(sort_col, ascending=sort_asc, na_position="last")

    # Result count hint
    total = len(summary[summary["_has_data"]])
    shown = len(has_data)
    st.caption(
        f"Showing **{shown}** of {total} tickers"
        + (f" matching `{search.strip()}`" if search.strip() else "")
        + f"  ·  sorted by **{sort_label}**"
    )

    # ── Expanders ─────────────────────────────────────────────────────────────
    if has_data.empty:
        st.info("No tickers match your search.")
    else:
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
                f"Range {row['_range_pct']:+.1f}%  ·  "
                f"{row['Date Range']}  ({row['Trading Days']} days)"
            )
            with st.expander(label, expanded=False):
                render_ticker_chart(ok_df, ticker, key_suffix=ticker)

    # ── Error tickers (collapsed) ─────────────────────────────────────────────
    if not no_data.empty:
        with st.expander(
            f"❌ {len(no_data)} ticker(s) with no data / ERROR", expanded=False
        ):
            for _, row in no_data.iterrows():
                st.write(f"**{row['Ticker']}** — `{row['Status']}`")


main()
