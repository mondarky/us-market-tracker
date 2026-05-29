"""
core/holdings.py
================
Single source of truth for all position data.
Reads from data/trade_log.csv and exposes clean DataFrames
for use by Portfolio, Performance, and any future pages.

Trade log schema (data/trade_log.csv):
    date              – YYYY-MM-DD, trade execution date
    ticker            – e.g. AVUV
    action            – BUY or SELL
    shares            – float, number of shares
    price_per_share   – float, execution price
    fees              – float, default 0.0
    portfolio         – e.g. "Growth ETFs", "Speculative"
    account           – e.g. "Brokerage", "IRA"
    notes             – free text, optional (e.g. "ESPP redeployment")

No Streamlit imports — pure pandas.
All functions return DataFrames or scalars; pages handle display.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_TRADE_LOG_PATH = Path("data/trade_log.csv")

TRADE_LOG_DTYPES = {
    "ticker": str,
    "action": str,
    "shares": float,
    "price_per_share": float,
    "fees": float,
    "portfolio": str,
    "account": str,
    "notes": str,
}

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_trade_log(path: str | Path = DEFAULT_TRADE_LOG_PATH) -> pd.DataFrame:
    """
    Load and validate trade_log.csv.
    Returns a clean DataFrame sorted by date ascending.
    Raises FileNotFoundError if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Trade log not found at '{path}'. "
            "Create data/trade_log.csv with columns: "
            "date, ticker, action, shares, price_per_share, fees, portfolio, account, notes"
        )

    df = pd.read_csv(path, dtype={"ticker": str, "action": str, "portfolio": str,
                                   "account": str, "notes": str})

    # Normalise
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["action"] = df["action"].str.upper().str.strip()
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
    df["price_per_share"] = pd.to_numeric(df["price_per_share"], errors="coerce").fillna(0.0)
    df["fees"] = pd.to_numeric(df["fees"], errors="coerce").fillna(0.0)
    df["portfolio"] = df["portfolio"].fillna("Default")
    df["account"] = df["account"].fillna("Brokerage")
    df["notes"] = df["notes"].fillna("")

    # Derived column: signed shares (negative for sells, for net calculations)
    df["signed_shares"] = df.apply(
        lambda r: r["shares"] if r["action"] == "BUY" else -r["shares"], axis=1
    )

    return df.sort_values("date").reset_index(drop=True)


def save_trade_log(df: pd.DataFrame, path: str | Path = DEFAULT_TRADE_LOG_PATH) -> None:
    """Persist trade log back to CSV (drops the derived signed_shares column)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "ticker", "action", "shares", "price_per_share",
            "fees", "portfolio", "account", "notes"]
    df[cols].to_csv(path, index=False, date_format="%Y-%m-%d")


def create_empty_trade_log(path: str | Path = DEFAULT_TRADE_LOG_PATH) -> pd.DataFrame:
    """
    Create an empty trade log CSV with correct headers.
    Useful for first-run initialisation.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(columns=[
        "date", "ticker", "action", "shares", "price_per_share",
        "fees", "portfolio", "account", "notes"
    ])
    df.to_csv(path, index=False)
    return df


def migrate_from_holdings_csv(
    holdings_path: str | Path,
    trade_log_path: str | Path = DEFAULT_TRADE_LOG_PATH,
    backfill_date: str = "2026-01-01",
    portfolio_col: str = "portfolio",
    account_col: str = "account",
) -> pd.DataFrame:
    """
    One-time migration helper.
    Reads old holdings.csv (ticker, shares, avg_cost, portfolio, account)
    and writes one BUY row per holding into a new trade_log.csv.

    backfill_date is used as the trade date for all migrated rows.
    Review and adjust dates manually after migration.
    """
    hdf = pd.read_csv(holdings_path)
    hdf.columns = hdf.columns.str.lower().str.strip()

    rows = []
    for _, row in hdf.iterrows():
        rows.append({
            "date": backfill_date,
            "ticker": str(row.get("ticker", "")).upper().strip(),
            "action": "BUY",
            "shares": float(row.get("shares", 0)),
            "price_per_share": float(row.get("avg_cost", row.get("avg cost", 0))),
            "fees": 0.0,
            "portfolio": row.get(portfolio_col, "Default"),
            "account": row.get(account_col, "Brokerage"),
            "notes": "migrated from holdings.csv",
        })

    trade_log = pd.DataFrame(rows)
    save_trade_log(trade_log, trade_log_path)
    return trade_log


# ---------------------------------------------------------------------------
# Core derived views
# ---------------------------------------------------------------------------

def get_open_positions(
    trade_log: pd.DataFrame,
    as_of: Optional[str | pd.Timestamp] = None,
) -> pd.DataFrame:
    """
    Derive current open positions from the trade log.
    If as_of is provided, only trades up to that date are included.

    Returns one row per (ticker, portfolio, account) with:
        ticker, portfolio, account,
        shares          – total open shares (BUY - SELL)
        lots            – number of BUY transactions contributing to open position
        avg_cost        – weighted average cost of open shares (FIFO cost basis)
        total_cost      – shares × avg_cost  (cost basis)
        first_buy_date  – earliest buy date
        last_trade_date – most recent trade date
    """
    df = trade_log.copy()

    if as_of is not None:
        as_of = pd.Timestamp(as_of)
        df = df[df["date"] <= as_of]

    if df.empty:
        return pd.DataFrame(columns=[
            "ticker", "portfolio", "account", "shares", "lots",
            "avg_cost", "total_cost", "first_buy_date", "last_trade_date"
        ])

    results = []
    groups = df.groupby(["ticker", "portfolio", "account"], sort=False)

    for (ticker, portfolio, account), grp in groups:
        grp = grp.sort_values("date")

        # FIFO lot tracking
        buy_lots: list[dict] = []   # list of {shares, price}
        total_fees = 0.0

        for _, trade in grp.iterrows():
            if trade["action"] == "BUY":
                buy_lots.append({
                    "shares": trade["shares"],
                    "price": trade["price_per_share"],
                    "date": trade["date"],
                })
                total_fees += trade["fees"]
            elif trade["action"] == "SELL":
                remaining_sell = trade["shares"]
                total_fees += trade["fees"]
                while remaining_sell > 0 and buy_lots:
                    if buy_lots[0]["shares"] <= remaining_sell:
                        remaining_sell -= buy_lots[0]["shares"]
                        buy_lots.pop(0)
                    else:
                        buy_lots[0]["shares"] -= remaining_sell
                        remaining_sell = 0

        # Aggregate open lots
        open_shares = sum(lot["shares"] for lot in buy_lots)

        if open_shares < 1e-6:
            # Fully closed position — skip from open positions view
            continue

        weighted_cost = (
            sum(lot["shares"] * lot["price"] for lot in buy_lots) / open_shares
            if open_shares > 0 else 0.0
        )

        results.append({
            "ticker": ticker,
            "portfolio": portfolio,
            "account": account,
            "shares": round(open_shares, 6),
            "lots": len(buy_lots),
            "avg_cost": round(weighted_cost, 4),
            "total_cost": round(open_shares * weighted_cost, 4),
            "first_buy_date": grp[grp["action"] == "BUY"]["date"].min(),
            "last_trade_date": grp["date"].max(),
        })

    return pd.DataFrame(results).sort_values("ticker").reset_index(drop=True)


def get_realized_pnl(trade_log: pd.DataFrame) -> pd.DataFrame:
    """
    Compute realized P/L for all fully or partially closed positions using FIFO.

    Returns one row per SELL event with:
        date, ticker, portfolio, account,
        shares_sold, sell_price, cost_basis_per_share,
        realized_pnl, realized_pnl_pct, notes
    """
    results = []
    groups = trade_log.groupby(["ticker", "portfolio", "account"], sort=False)

    for (ticker, portfolio, account), grp in groups:
        grp = grp.sort_values("date")
        buy_lots: list[dict] = []

        for _, trade in grp.iterrows():
            if trade["action"] == "BUY":
                buy_lots.append({
                    "shares": trade["shares"],
                    "price": trade["price_per_share"],
                })
            elif trade["action"] == "SELL":
                remaining_sell = trade["shares"]
                cost_basis_total = 0.0
                shares_matched = 0.0

                while remaining_sell > 0 and buy_lots:
                    lot = buy_lots[0]
                    matched = min(lot["shares"], remaining_sell)
                    cost_basis_total += matched * lot["price"]
                    shares_matched += matched
                    remaining_sell -= matched
                    if lot["shares"] <= matched + 1e-9:
                        buy_lots.pop(0)
                    else:
                        lot["shares"] -= matched

                if shares_matched > 0:
                    avg_cost_basis = cost_basis_total / shares_matched
                    proceeds = trade["shares"] * trade["price_per_share"] - trade["fees"]
                    pnl = proceeds - cost_basis_total
                    pnl_pct = (pnl / cost_basis_total * 100) if cost_basis_total > 0 else 0.0

                    results.append({
                        "date": trade["date"],
                        "ticker": ticker,
                        "portfolio": portfolio,
                        "account": account,
                        "shares_sold": trade["shares"],
                        "sell_price": trade["price_per_share"],
                        "cost_basis_per_share": round(avg_cost_basis, 4),
                        "proceeds": round(proceeds, 4),
                        "realized_pnl": round(pnl, 4),
                        "realized_pnl_pct": round(pnl_pct, 4),
                        "notes": trade["notes"],
                    })

    return pd.DataFrame(results).sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Performance / time-series helpers
# ---------------------------------------------------------------------------

def get_portfolio_value_series(
    trade_log: pd.DataFrame,
    price_df: pd.DataFrame,
    portfolio: Optional[str] = None,
) -> pd.DataFrame:
    """
    Reconstruct portfolio value on each trading day using historical prices.

    Args:
        trade_log  – from load_trade_log()
        price_df   – long-format price history with columns:
                     [Ticker, Date, Close]
                     (built by loading and concatenating ticker_data_*.csv files)
        portfolio  – if provided, filter to a single portfolio; None = all portfolios

    Returns DataFrame with columns:
        date, market_value, cost_basis, unrealized_pnl, unrealized_pnl_pct
    """
    # Normalise price_df
    price_df = price_df.copy()
    price_df.columns = price_df.columns.str.strip()
    price_df["Date"] = pd.to_datetime(price_df["Date"]).dt.normalize()
    price_df["Ticker"] = price_df["Ticker"].str.upper().str.strip()

    tl = trade_log.copy()
    if portfolio:
        tl = tl[tl["portfolio"] == portfolio]

    trading_dates = sorted(price_df["Date"].unique())
    rows = []

    for date in trading_dates:
        positions = get_open_positions(tl, as_of=date)
        if positions.empty:
            continue

        # Join with prices on this date
        day_prices = price_df[price_df["Date"] == date][["Ticker", "Close"]].copy()
        merged = positions.merge(day_prices, left_on="ticker", right_on="Ticker", how="left")

        # Drop tickers with no price data for this date
        merged = merged.dropna(subset=["Close"])
        if merged.empty:
            continue

        market_value = (merged["shares"] * merged["Close"]).sum()
        cost_basis = merged["total_cost"].sum()
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        rows.append({
            "date": date,
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "unrealized_pnl": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 4),
        })

    return pd.DataFrame(rows).reset_index(drop=True)


def get_ticker_value_series(
    trade_log: pd.DataFrame,
    price_df: pd.DataFrame,
    ticker: str,
) -> pd.DataFrame:
    """
    Same as get_portfolio_value_series but scoped to a single ticker.
    Useful for the per-ticker performance drilldown.
    """
    tl = trade_log[trade_log["ticker"] == ticker.upper()]
    return get_portfolio_value_series(tl, price_df)


# ---------------------------------------------------------------------------
# Convenience aggregates (used by Portfolio page summary metrics)
# ---------------------------------------------------------------------------

def get_summary(
    open_positions: pd.DataFrame,
    price_df: pd.DataFrame,
    as_of_date: Optional[str | pd.Timestamp] = None,
) -> dict:
    """
    Return a dict of top-level summary metrics for the Portfolio page header.

    Args:
        open_positions – from get_open_positions()
        price_df       – price history DataFrame [Ticker, Date, Close]
        as_of_date     – use latest available date if None
    """
    price_df = price_df.copy()
    price_df["Date"] = pd.to_datetime(price_df["Date"]).dt.normalize()
    price_df["Ticker"] = price_df["Ticker"].str.upper().str.strip()

    if as_of_date is None:
        as_of_date = price_df["Date"].max()
    else:
        as_of_date = pd.Timestamp(as_of_date)

    latest_prices = (
        price_df[price_df["Date"] <= as_of_date]
        .sort_values("Date")
        .groupby("Ticker")["Close"]
        .last()
        .reset_index()
    )
    latest_prices.columns = ["ticker", "current_price"]

    merged = open_positions.merge(latest_prices, on="ticker", how="left")
    merged["market_value"] = merged["shares"] * merged["current_price"]
    merged["unrealized_pnl"] = merged["market_value"] - merged["total_cost"]

    total_cost = merged["total_cost"].sum()
    total_mv = merged["market_value"].sum()
    total_pnl = total_mv - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    return {
        "total_cost_basis": round(total_cost, 2),
        "total_market_value": round(total_mv, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
        "total_unrealized_pnl_pct": round(total_pnl_pct, 4),
        "num_tickers": merged["ticker"].nunique(),
        "num_lots": int(merged["lots"].sum()),
        "num_portfolios": merged["portfolio"].nunique(),
        "as_of_date": as_of_date.strftime("%Y-%m-%d"),
    }
