"""
Portfolio calculations — pure Python/pandas, no Streamlit, no I/O.
All functions are safe to unit-test independently.
"""
import pandas as pd


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
    holdings: pd.DataFrame,
    prices_df,
    portfolio_filter: str | None = None,
) -> pd.DataFrame:
    """
    Aggregate lots, attach current prices, compute unrealised P/L.

    portfolio_filter=None  → group by (Portfolio, Ticker) — "All" view
    portfolio_filter="X"   → filter to X, group by Ticker — single-portfolio view
    Always includes a "Portfolio" column in the output.
    """
    if holdings.empty:
        return pd.DataFrame()

    src = (holdings if portfolio_filter is None
           else holdings[holdings["portfolio"] == portfolio_filter])
    if src.empty:
        return pd.DataFrame()

    multi_key = portfolio_filter is None
    group_by  = ["portfolio", "ticker"] if multi_key else "ticker"

    rows = []
    for keys, group in src.groupby(group_by, sort=True):
        if multi_key:
            pf_name, ticker = keys   # tuple from multi-column groupby
        else:
            ticker  = keys           # scalar from single-column groupby
            pf_name = portfolio_filter

        total_shares = group["shares"].sum()
        if total_shares < 0.00001:
            continue

        wavg_cost = (group["shares"] * group["avg_cost"]).sum() / total_shares
        accts = ", ".join(
            sorted({str(a) for a in group["account"].dropna()
                    if str(a).strip() and str(a) != "nan"})
        )
        cur_px  = latest_close(prices_df, ticker) if prices_df is not None else None
        cost    = total_shares * wavg_cost
        mkt_val = total_shares * cur_px if cur_px is not None else None
        pl_d    = mkt_val - cost if mkt_val is not None else None
        pl_pct  = pl_d / cost * 100 if (cost > 0 and pl_d is not None) else None

        rows.append({
            "Portfolio":     pf_name,
            "Ticker":        ticker,
            "Lots":          len(group),
            "Shares":        total_shares,
            "Avg Cost":      wavg_cost,
            "Current Price": cur_px,
            "Cost Basis":    cost,
            "Market Value":  mkt_val,
            "P/L $":         pl_d,
            "P/L %":         pl_pct,
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
