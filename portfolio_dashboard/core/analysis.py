"""
Portfolio calculations — pure Python/pandas, no Streamlit, no I/O.
All functions are safe to unit-test independently.
"""
import pandas as pd
from core.holdings import get_open_positions


def latest_close(prices_df: pd.DataFrame, ticker: str) -> float | None:
    """Return the most recent Close price for a ticker (OK rows only)."""
    mask = (
        (prices_df["Ticker"].str.upper() == ticker.upper())
        & prices_df["fetch_status"].str.startswith("OK", na=False)
    )
    rows = prices_df[mask]
    if rows.empty:
        return None
    try:
        return float(rows.sort_values("Date").iloc[-1]["Close"])
    except Exception:
        return None


def build_portfolio(
    trade_log: pd.DataFrame,
    prices_df,
    portfolio_filter: str | None = None,
) -> pd.DataFrame:
    """
    Derive open positions from the trade log via FIFO, attach current prices,
    compute unrealised P/L.

    portfolio_filter=None  → group by (Portfolio, Ticker) — "All" view
    portfolio_filter="X"   → filter to X — single-portfolio view
    Always includes a "Portfolio" column in the output.
    """
    if trade_log.empty:
        return pd.DataFrame()

    # FIFO open positions per (ticker × portfolio × account)
    positions = get_open_positions(trade_log)
    if positions.empty:
        return pd.DataFrame()

    if portfolio_filter is not None:
        positions = positions[positions["portfolio"] == portfolio_filter]
        if positions.empty:
            return pd.DataFrame()

    # Aggregate across accounts within each (portfolio, ticker)
    multi_key = portfolio_filter is None
    group_by  = ["portfolio", "ticker"] if multi_key else "ticker"

    rows = []
    for keys, grp in positions.groupby(group_by, sort=True):
        if multi_key:
            pf_name, ticker = keys   # tuple from multi-column groupby
        else:
            ticker  = keys           # scalar from single-column groupby
            pf_name = portfolio_filter

        total_shares = grp["shares"].sum()
        if total_shares < 0.00001:
            continue

        total_cost = grp["total_cost"].sum()
        wavg_cost  = total_cost / total_shares   # weighted avg across accounts
        accts      = ", ".join(sorted(grp["account"].dropna().astype(str).unique()))

        cur_px  = latest_close(prices_df, ticker) if prices_df is not None else None
        mkt_val = total_shares * cur_px if cur_px is not None else None
        pl_d    = mkt_val - total_cost if mkt_val is not None else None
        pl_pct  = pl_d / total_cost * 100 if (total_cost > 0 and pl_d is not None) else None

        rows.append({
            "Portfolio":     pf_name,
            "Ticker":        ticker,
            "Lots":          int(grp["lots"].sum()),
            "Shares":        round(total_shares, 6),
            "Avg Cost":      round(wavg_cost, 4),
            "Current Price": cur_px,
            "Cost Basis":    round(total_cost, 4),
            "Market Value":  round(mkt_val, 2)   if mkt_val is not None else None,
            "P/L $":         round(pl_d, 2)       if pl_d    is not None else None,
            "P/L %":         round(pl_pct, 4)     if pl_pct  is not None else None,
            "Account(s)":    accts,
            "_has_price":    cur_px is not None,
        })

    return pd.DataFrame(rows)


def portfolio_summary(port: pd.DataFrame) -> pd.DataFrame:
    """Roll up per-(portfolio, ticker) rows to one summary row per portfolio."""
    rows = []
    for pf, grp in port.groupby("Portfolio"):
        priced    = grp[grp["_has_price"]]
        cost_all  = grp["Cost Basis"].sum()
        cost_prcd = priced["Cost Basis"].sum()
        mkt       = priced["Market Value"].sum() if not priced.empty else None
        pl_d      = (mkt - cost_prcd) if mkt is not None else None
        pl_pct    = (pl_d / cost_prcd * 100
                     if (pl_d is not None and cost_prcd > 0) else None)
        rows.append({
            "Portfolio":    pf,
            "Positions":    len(grp),
            "Cost Basis":   cost_all,
            "Market Value": mkt,
            "P/L $":        pl_d,
            "P/L %":        pl_pct,
        })
    return pd.DataFrame(rows)
