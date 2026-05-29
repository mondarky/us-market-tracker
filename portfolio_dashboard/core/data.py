"""
Data I/O — file discovery, loading, saving, and market summary building.

Uses @st.cache_data for performance (Streamlit dependency is intentional here;
the caching layer belongs with the I/O layer for a solo project).
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

# ── Canonical paths (resolved from this file's location) ──────────────────────
_PKG_ROOT        = Path(__file__).parent.parent          # portfolio_dashboard/
FETCHER_DIR      = _PKG_ROOT.parent / "ticker_fetcher"   # ../ticker_fetcher/
DATA_DIR         = _PKG_ROOT / "data"
TICKER_PRICE_DIR = DATA_DIR / "ticker_price"
TRADE_LOG_FILE   = DATA_DIR / "trade_log.csv"


# ── Trade log I/O ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_trade_log() -> pd.DataFrame:
    """
    Load trade_log.csv with caching (TTL 5 min).
    Creates an empty file with correct headers if it doesn't exist yet.
    The returned DataFrame includes a derived 'signed_shares' column.
    """
    from core.holdings import load_trade_log as _load, create_empty_trade_log
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRADE_LOG_FILE.exists():
        return create_empty_trade_log(TRADE_LOG_FILE)
    try:
        return _load(TRADE_LOG_FILE)
    except FileNotFoundError:
        return create_empty_trade_log(TRADE_LOG_FILE)


def save_trade_log(df: pd.DataFrame) -> None:
    """
    Persist the edited trade log.
    Converts date objects → Timestamps so date_format='%Y-%m-%d' applies cleanly.
    """
    from core.holdings import save_trade_log as _save
    save_df = df.copy()
    if "date" in save_df.columns:
        save_df["date"] = pd.to_datetime(save_df["date"], errors="coerce")
    _save(save_df, TRADE_LOG_FILE)


# ── Price data ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_prices() -> tuple:
    """
    Find and load the most-recently dated ticker CSV from data/ticker_price/.
    Returns (DataFrame | None, filename | None, file_date | None).
    Auto-picks the newest file by reverse-sorted filename (YYYYMMDD suffix).
    """
    csvs = sorted(TICKER_PRICE_DIR.glob("ticker_data_*.csv"), reverse=True)
    if not csvs:
        return None, None, None
    path = csvs[0]
    df   = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    stem = path.stem   # e.g. "ticker_data_20260529"
    try:
        fdate = date(int(stem[-8:-4]), int(stem[-4:-2]), int(stem[-2:]))
    except Exception:
        fdate = None
    return df, path.name, fdate


# ── Market summary ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def build_market_summary(prices_df) -> pd.DataFrame:
    """
    Build a one-row-per-ticker summary from the price CSV.
    Handles any number of tickers and any date range (1 mo, 6 mo, 1 yr …).
    Tickers with ERROR status appear with N/A price columns.
    """
    if prices_df is None or (isinstance(prices_df, pd.DataFrame) and prices_df.empty):
        return pd.DataFrame()

    rows = []
    for ticker, grp in prices_df.groupby("Ticker", sort=True):
        ok         = grp[grp["fetch_status"].str.startswith("OK", na=False)].copy()
        raw_status = grp["fetch_status"].iloc[0]

        if ok.empty or ok["Date"].isna().all():
            rows.append({
                "Ticker":       ticker,   "Status":       raw_status,
                "Trading Days": 0,        "Date Range":   "—",
                "Latest Close": None,     "Period High":  None,
                "Period Low":   None,     "_has_data":    False,
            })
            continue

        ok     = ok.dropna(subset=["Date"]).sort_values("Date")
        d_from = ok["Date"].iloc[0].date()
        d_to   = ok["Date"].iloc[-1].date()

        date_range = (
            f"{d_from.strftime('%d %b')} – {d_to.strftime('%d %b %y')}"
            if d_from.year == d_to.year
            else f"{d_from.strftime('%d %b %y')} – {d_to.strftime('%d %b %y')}"
        )

        rows.append({
            "Ticker":       ticker,
            "Status":       raw_status,
            "Trading Days": len(ok),
            "Date Range":   date_range,
            "Latest Close": float(ok["Close"].iloc[-1]),
            "Period High":  float(ok["High"].max()) if "High" in ok.columns else float(ok["Close"].max()),
            "Period Low":   float(ok["Low"].min())  if "Low"  in ok.columns else float(ok["Close"].min()),
            "_has_data":    True,
        })

    return pd.DataFrame(rows)
