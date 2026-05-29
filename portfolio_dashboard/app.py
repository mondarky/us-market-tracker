"""
Investment Portfolio Dashboard — home page / entry point.

Run:
    streamlit run app.py

Streamlit auto-discovers pages/ and renders navigation in the sidebar:
    📈 Portfolio    → pages/1_Portfolio.py
    📊 Market Data  → pages/2_Market_Data.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from datetime import date

from core.data import load_prices, load_holdings

st.set_page_config(
    page_title="Investment Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("📈 Investment Portfolio Dashboard")
st.caption(f"Today: {date.today().strftime('%B %d, %Y')}")

st.info("👈 Open the sidebar to navigate between **Portfolio** and **Market Data** pages.")

st.markdown("---")

# ── Quick status overview ─────────────────────────────────────────────────────
prices_df, price_file, price_date = load_prices()
holdings = load_holdings()

c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("📋 Holdings")
    if holdings.empty:
        st.write("No positions loaded.")
    else:
        n_lots      = len(holdings)
        n_tickers   = holdings["ticker"].nunique()
        n_portfolios = holdings["portfolio"].nunique()
        st.metric("Lots",       n_lots)
        st.metric("Tickers",    n_tickers)
        st.metric("Portfolios", n_portfolios)

with c2:
    st.subheader("📡 Price Data")
    if prices_df is None:
        st.error("No price CSV found.\nRun `fetch_tickers.py`.")
    else:
        n_tracked = prices_df["Ticker"].nunique()
        gap       = (date.today() - price_date).days if price_date else None
        freshness = f"✅ Fresh ({price_date})" if gap is not None and gap <= 3 else \
                    f"⚠️ Stale — {gap}d old" if gap is not None else "Unknown"
        st.metric("Tickers tracked", n_tracked)
        st.write(f"**File:** `{price_file}`")
        st.write(f"**Status:** {freshness}")

with c3:
    st.subheader("📂 Data Location")
    st.write("**Holdings:**")
    st.code("data/holdings/holdings.csv")
    st.write("**Ticker prices:**")
    st.code("data/ticker_price/ticker_data_YYYYMMDD.csv")
    st.write("**Fetcher script:**")
    st.code("../ticker_fetcher/fetch_tickers.py")
