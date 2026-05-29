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


@st.cache_data(ttl=3600)   # 1-hour cache — daily rate is sufficient
def load_fx_rates() -> dict:
    """
    Fetch current USD → THB / JPY / HKD exchange rates via yfinance.
    Returns {"USD": 1.0, "THB": float|None, "JPY": float|None, "HKD": float|None}.
    None means the rate could not be fetched; the UI will hide that option.
    Cached for 1 hour — no need for real-time rates.
    """
    import yfinance as yf
    pairs = {"THB": "USDTHB=X", "JPY": "USDJPY=X", "HKD": "USDHKD=X"}
    rates: dict = {"USD": 1.0}
    for code, ticker in pairs.items():
        try:
            rates[code] = float(yf.Ticker(ticker).fast_info["last_price"])
        except Exception:
            try:
                hist = yf.Ticker(ticker).history(period="2d")["Close"].dropna()
                rates[code] = float(hist.iloc[-1]) if not hist.empty else None
            except Exception:
                rates[code] = None
    return rates


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
    Load and stitch ALL ticker CSVs from data/ticker_price/.
    Deduplicates by (Ticker, Date), keeping the row from the most recently
    fetched CSV — so each date always reflects the latest fetch's OHLCV and
    fetch_status.  As more CSVs accumulate the historical depth grows
    automatically without any manual configuration.

    Returns (stitched_df | None, label | None, latest_file_date | None).
    label is  "ticker_data_YYYYMMDD.csv"  for one file, or
              "N files (YYYYMMDD → YYYYMMDD)"  for multiple.
    """
    csvs = sorted(TICKER_PRICE_DIR.glob("ticker_data_*.csv"), reverse=True)
    # reverse=True → index 0 = newest file
    if not csvs:
        return None, None, None

    frames = []
    for rank, path in enumerate(csvs):   # rank 0 = newest
        df = pd.read_csv(path)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["_rank"] = rank
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Keep the row from the newest CSV (lowest rank) for each (Ticker, Date) pair
    combined = (
        combined
        .sort_values("_rank")                                      # newest first
        .drop_duplicates(subset=["Ticker", "Date"], keep="first")  # keep newest
        .drop(columns=["_rank"])
        .sort_values(["Ticker", "Date"])
        .reset_index(drop=True)
    )

    # Date of the newest file (used for freshness check)
    stem = csvs[0].stem   # e.g. "ticker_data_20260529"
    try:
        fdate = date(int(stem[-8:-4]), int(stem[-4:-2]), int(stem[-2:]))
    except Exception:
        fdate = None

    if len(csvs) == 1:
        label = csvs[0].name
    else:
        oldest_stem = csvs[-1].stem
        label = f"{len(csvs)} files ({oldest_stem[-8:]} → {stem[-8:]})"

    return combined, label, fdate


# ── Performance series ────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_performance_series(
    trade_log,
    prices_df,
    portfolio: str | None = None,
) -> pd.DataFrame:
    """
    Cached wrapper for get_portfolio_value_series().

    Iterates over every trading date present in prices_df and reconstructs
    open positions (FIFO) as of that date, then multiplies by the day's Close.
    Must be cached — the inner loop is O(dates × trades).

    Returns DataFrame: date, market_value, cost_basis,
                       unrealized_pnl, unrealized_pnl_pct
    """
    from core.holdings import get_portfolio_value_series
    if trade_log is None or prices_df is None:
        return pd.DataFrame()
    if (isinstance(trade_log, pd.DataFrame) and trade_log.empty) or \
       (isinstance(prices_df, pd.DataFrame) and prices_df.empty):
        return pd.DataFrame()

    # Python 3.14 + pandas 2.x default pd.to_datetime() to datetime64[us].
    # get_open_positions() uses pd.Timestamp for the as_of comparison, which is
    # internally datetime64[ns], causing a unit-mismatch TypeError.
    # yfinance also returns timezone-aware (UTC) dates; strip tz before casting.
    def _to_naive_ns(series: pd.Series) -> pd.Series:
        s = pd.to_datetime(series, errors="coerce")
        if s.dt.tz is not None:                        # strip UTC / any tz
            s = s.dt.tz_convert("UTC").dt.tz_localize(None)
        return s.astype("datetime64[ns]")

    tl = trade_log.copy()
    p  = prices_df.copy()
    tl["date"] = _to_naive_ns(tl["date"])
    p["Date"]  = _to_naive_ns(p["Date"])

    return get_portfolio_value_series(tl, p, portfolio=portfolio)


# ── Market summary ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def build_market_summary(prices_df) -> pd.DataFrame:
    """
    Build a one-row-per-ticker summary from the (stitched) price DataFrame.
    fetch_status is taken from the row with the latest Date for each ticker,
    so it always reflects the most recent fetch run.
    """
    if prices_df is None or (isinstance(prices_df, pd.DataFrame) and prices_df.empty):
        return pd.DataFrame()

    rows = []
    for ticker, grp in prices_df.groupby("Ticker", sort=True):
        ok = grp[grp["fetch_status"].str.startswith("OK", na=False)].copy()

        # Use status from the latest-dated row (= most recent CSV after stitching)
        latest_row = grp.dropna(subset=["Date"]).sort_values("Date").iloc[-1]
        raw_status = latest_row["fetch_status"]

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
