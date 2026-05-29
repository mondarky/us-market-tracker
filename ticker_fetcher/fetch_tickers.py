"""
Fetch stock ticker data using yfinance.
Reads tickers from tickers.txt, exports results to CSV with fetch status.

Flags applied per ticker (recorded in fetch_status column):
  OK              — clean fetch, data is fresh, ≥ 20 trading sessions
  OK|STALE        — fetched OK but latest date is > 3 calendar days behind today
  OK|SHORT        — fetched OK but fewer than 20 trading sessions of history
  OK|STALE|SHORT  — both stale and short history
  ERROR           — fetch failed entirely
"""

import sys
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance is not installed. Run: pip install yfinance")

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas is not installed. Run: pip install pandas")


# --- Configuration ---
SCRIPT_DIR   = Path(__file__).parent
TICKER_FILE  = SCRIPT_DIR / "tickers.txt"
# Output goes into the dashboard's data folder so the app picks it up automatically
OUTPUT_DIR   = SCRIPT_DIR.parent / "portfolio_dashboard" / "data" / "ticker_price"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE  = OUTPUT_DIR / f"ticker_data_{date.today().strftime('%Y%m%d')}.csv"
PERIOD       = "1mo"   # how much history to fetch per ticker
INTERVAL     = "1d"    # data granularity

STALE_DAYS        = 3   # calendar-day gap that triggers STALE flag
SHORT_HISTORY_MIN = 20  # trading sessions below which SHORT flag is applied

# Columns yfinance adds that we don't want in the output
DROP_COLUMNS = {"Dividends", "Stock Splits", "Capital Gains"}


def load_tickers(path: Path) -> list[str]:
    if not path.exists():
        sys.exit(f"Ticker file not found: {path}")
    tickers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            symbol = line.strip().upper()
            if symbol and not symbol.startswith("#"):
                tickers.append(symbol)
    if not tickers:
        sys.exit("Ticker file is empty — nothing to fetch.")
    return tickers


def build_status(flags: list[str]) -> str:
    """Combine base status with any warning flags, e.g. 'OK|STALE|SHORT'."""
    return "|".join(flags)


def fetch_ticker(
    symbol: str,
    run_date: date,
) -> tuple[pd.DataFrame | None, str, str | None, list[str]]:
    """
    Returns (df, base_status, error_message, warning_flags).
    warning_flags is a list of zero or more strings like ['STALE', 'SHORT'].
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=PERIOD, interval=INTERVAL, auto_adjust=True)

        if df.empty:
            return None, "ERROR", "No data returned (ticker may be invalid or delisted)", []

        df = df.reset_index()

        # --- Drop unwanted columns ---
        cols_to_drop = [c for c in df.columns if c in DROP_COLUMNS]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)

        warnings: list[str] = []

        # --- Staleness check ---
        latest_date = pd.to_datetime(df["Date"]).dt.date.max()
        gap_days = (run_date - latest_date).days
        if gap_days > STALE_DAYS:
            warnings.append("STALE")

        # --- Short history check ---
        session_count = len(df)
        if session_count < SHORT_HISTORY_MIN:
            warnings.append("SHORT")

        return df, "OK", None, warnings

    except Exception as exc:
        return None, "ERROR", str(exc), []


def main() -> None:
    run_date = date.today()
    tickers  = load_tickers(TICKER_FILE)

    print(f"Loaded {len(tickers)} ticker(s) from {TICKER_FILE.name}")
    print(f"Fetching {PERIOD} of {INTERVAL} data  [run date: {run_date}]\n")

    results: list[pd.DataFrame] = []
    ok_clean:  list[str]        = []
    ok_stale:  dict[str, str]   = {}   # symbol -> latest date string
    ok_short:  dict[str, int]   = {}   # symbol -> session count
    errors:    dict[str, str]   = {}   # symbol -> error message

    for i, symbol in enumerate(tickers, 1):
        print(f"  [{i:>3}/{len(tickers)}] {symbol:<15}", end=" ", flush=True)
        df, base_status, err, warnings = fetch_ticker(symbol, run_date)

        if base_status == "OK":
            final_status = build_status(["OK"] + warnings)
            df.insert(0, "Ticker", symbol)
            df["fetch_status"] = final_status

            results.append(df)

            if not warnings:
                ok_clean.append(symbol)
            if "STALE" in warnings:
                latest = pd.to_datetime(df["Date"]).dt.date.max().isoformat()
                ok_stale[symbol] = latest
            if "SHORT" in warnings:
                ok_short[symbol] = len(df)

            tag = f"  ({len(df)} rows)" if not warnings else f"  ({len(df)} rows)  ⚠ {', '.join(warnings)}"
            print(f"{final_status}{tag}")

        else:
            errors[symbol] = err
            error_row = pd.DataFrame([{
                "Ticker":       symbol,
                "Date":         pd.NaT,
                "fetch_status": "ERROR",
                "error_detail": err,
            }])
            results.append(error_row)
            print(f"ERROR — {err}")

    # --- Build final DataFrame ---
    final = pd.concat(results, ignore_index=True)

    # Reorder: Ticker and fetch_status first, rest of OHLCV columns after
    priority   = ["Ticker", "fetch_status"]
    other_cols = [c for c in final.columns if c not in priority]
    final      = final[priority + other_cols]

    final.to_csv(OUTPUT_FILE, index=False)

    # --- Summary ---
    sep = "=" * 65
    print(f"\n{sep}")
    print("SUMMARY")
    print(sep)
    print(f"  Total tickers      : {len(tickers)}")
    print(f"  OK (clean)         : {len(ok_clean)}")
    print(f"  OK with warnings   : {len(ok_stale) + len(ok_short) - len(set(ok_stale) & set(ok_short))}"
          f"  (STALE: {len(ok_stale)}, SHORT: {len(ok_short)})")
    print(f"  Failed (ERROR)     : {len(errors)}")
    print(f"  Output file        : portfolio_dashboard/data/ticker_price/{OUTPUT_FILE.name}")
    print(f"  Total rows written : {len(final)}")
    print(f"  Run completed at   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if ok_stale:
        print(f"\n{sep}")
        print(f"STALE DATA  (latest date > {STALE_DAYS} calendar days behind {run_date})")
        print(sep)
        for symbol, latest in ok_stale.items():
            gap = (run_date - date.fromisoformat(latest)).days
            print(f"  {symbol:<15} latest={latest}  ({gap} days behind)")

    if ok_short:
        print(f"\n{sep}")
        print(f"SHORT HISTORY  (fewer than {SHORT_HISTORY_MIN} trading sessions)")
        print(sep)
        for symbol, count in ok_short.items():
            print(f"  {symbol:<15} {count} session(s) of history")

    if errors:
        print(f"\n{sep}")
        print("ERROR REPORT")
        print(sep)
        for symbol, msg in errors.items():
            print(f"  {symbol:<15} {msg}")

    print(sep)


if __name__ == "__main__":
    main()
