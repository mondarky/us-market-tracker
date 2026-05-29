"""
Data I/O — file discovery, loading, saving, and market summary building.

Uses @st.cache_data for performance (Streamlit dependency is intentional here;
the caching layer belongs with the I/O layer for a solo project).
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

from core.utils import HOLDINGS_COLS

# ── Canonical paths (resolved from this file's location) ──────────────────────
_PKG_ROOT        = Path(__file__).parent.parent          # portfolio_dashboard/
FETCHER_DIR      = _PKG_ROOT.parent / "ticker_fetcher"   # ../ticker_fetcher/
DATA_DIR         = _PKG_ROOT / "data"
HOLDINGS_DIR     = DATA_DIR / "holdings"
TICKER_PRICE_DIR = DATA_DIR / "ticker_price"
HOLDINGS_FILE    = HOLDINGS_DIR / "holdings.csv"


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


# ── Holdings data ─────────────────────────────────────────────────────────────

def load_holdings() -> pd.DataFrame:
    """Load holdings.csv; create file with headers if missing."""
    HOLDINGS_DIR.mkdir(parents=True, exist_ok=True)
    if not HOLDINGS_FILE.exists():
        empty = pd.DataFrame(columns=HOLDINGS_COLS)
        empty.to_csv(HOLDINGS_FILE, index=False)
        return empty

    df = pd.read_csv(HOLDINGS_FILE, dtype=str)
    df["shares"]        = pd.to_numeric(df.get("shares"),   errors="coerce").fillna(0)
    df["avg_cost"]      = pd.to_numeric(df.get("avg_cost"), errors="coerce").fillna(0)
    df["ticker"]        = df["ticker"].astype(str).str.strip().str.upper()
    # DateColumn requires date objects, not strings
    df["purchase_date"] = pd.to_datetime(
        df.get("purchase_date"), errors="coerce"
    ).dt.date
    # Normalise portfolio — blank / NaN → "Default"
    df["portfolio"] = (
        df["portfolio"].fillna("").astype(str).str.strip().replace("", "Default")
        if "portfolio" in df.columns
        else "Default"
    )
    for col in HOLDINGS_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[HOLDINGS_COLS]


def save_holdings(df: pd.DataFrame) -> None:
    """Persist holdings to CSV, converting date objects back to ISO strings."""
    HOLDINGS_DIR.mkdir(parents=True, exist_ok=True)
    save_df = df.copy()
    if "purchase_date" in save_df.columns:
        save_df["purchase_date"] = pd.to_datetime(
            save_df["purchase_date"], errors="coerce"
        ).apply(lambda d: d.strftime("%Y-%m-%d") if not pd.isnull(d) else "")
    save_df.to_csv(HOLDINGS_FILE, index=False)


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

        # Show year on both ends only when they differ
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
