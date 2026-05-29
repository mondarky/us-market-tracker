"""
Shared constants, format helpers, and pandas Styler functions.
No Streamlit imports — safe to use in tests and non-UI contexts.
"""
import pandas as pd
import plotly.express as px

# ── Constants ─────────────────────────────────────────────────────────────────
ACCOUNT_OPTIONS      = ["Brokerage", "IRA", "Roth IRA", "401k", "Other"]
HOLDINGS_COLS        = ["ticker", "shares", "avg_cost", "purchase_date",
                         "account", "portfolio", "notes"]
STALE_THRESHOLD_DAYS = 3
PALETTE              = px.colors.qualitative.Pastel   # stable cross-chart palette

# ── Format helpers ────────────────────────────────────────────────────────────
MONEY_FMT  = "${:,.2f}"
SHARES_FMT = lambda v: f"{v:,.5f}".rstrip("0").rstrip(".") if pd.notna(v) else "—"
OPT_MONEY  = lambda v: f"${v:,.2f}" if pd.notna(v) else "—"
PL_D_FMT   = lambda v: f"${v:+,.2f}" if pd.notna(v) else "—"
PL_P_FMT   = lambda v: f"{v:+.2f}%" if pd.notna(v) else "—"

# ── Colour helpers ────────────────────────────────────────────────────────────

def pl_color(val) -> str:
    """Return CSS colour string for a P/L value."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return "color: #27ae60; font-weight: 600"
    if v < 0:
        return "color: #e74c3c; font-weight: 600"
    return ""


def apply_pl_color(styler, cols: list[str]):
    """Apply pl_color — works with pandas <2.1 (applymap) and >=2.1 (map)."""
    valid = [c for c in cols if c in styler.data.columns]
    if not valid:
        return styler
    fn = getattr(styler, "map", getattr(styler, "applymap", None))
    return fn(pl_color, subset=valid) if fn else styler


# ── Styler functions ──────────────────────────────────────────────────────────

def style_holdings_table(df: pd.DataFrame, show_portfolio: bool = False):
    """Style the main per-ticker holdings table."""
    col_order = ["Portfolio", "Ticker", "Lots", "Shares", "Avg Cost",
                 "Current Price", "Cost Basis", "Market Value", "P/L $", "P/L %", "Account(s)"]
    if not show_portfolio:
        col_order = [c for c in col_order if c != "Portfolio"]
    display_cols = [c for c in col_order if c in df.columns]
    display = df[display_cols].copy()

    fmt = {
        "Lots":          "{:,d}",
        "Shares":        SHARES_FMT,
        "Avg Cost":      MONEY_FMT,
        "Current Price": OPT_MONEY,
        "Cost Basis":    MONEY_FMT,
        "Market Value":  OPT_MONEY,
        "P/L $":         PL_D_FMT,
        "P/L %":         PL_P_FMT,
    }
    fmt    = {k: v for k, v in fmt.items() if k in display_cols}
    styler = display.style.format(fmt, na_rep="—")
    styler = apply_pl_color(styler, ["P/L $", "P/L %"])

    right = [c for c in ["Lots", "Shares", "Avg Cost", "Current Price",
                          "Cost Basis", "Market Value", "P/L $", "P/L %"]
             if c in display_cols]
    left  = [c for c in ["Portfolio", "Ticker", "Account(s)"] if c in display_cols]
    if right: styler = styler.set_properties(**{"text-align": "right"}, subset=right)
    if left:  styler = styler.set_properties(**{"text-align": "left"},  subset=left)
    return styler


def style_portfolio_summary(df: pd.DataFrame):
    """Style the per-portfolio rollup table."""
    fmt = {
        "Positions":    "{:,d}",
        "Cost Basis":   MONEY_FMT,
        "Market Value": OPT_MONEY,
        "P/L $":        PL_D_FMT,
        "P/L %":        PL_P_FMT,
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styler = df.style.format(fmt, na_rep="—")
    return apply_pl_color(styler, ["P/L $", "P/L %"])


def style_market_summary(df: pd.DataFrame):
    """Style the market-data ticker summary table."""
    fmt = {
        "Latest Close": OPT_MONEY,
        "Period High":  OPT_MONEY,
        "Period Low":   OPT_MONEY,
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styler = df.style.format(fmt, na_rep="—")

    def _status_color(val) -> str:
        s = str(val)
        if s == "OK":             return "color: #27ae60; font-weight: 600"
        if s.startswith("OK|"):   return "color: #f39c12; font-weight: 600"
        if s == "ERROR":          return "color: #e74c3c; font-weight: 600"
        return ""

    fn = getattr(styler, "map", getattr(styler, "applymap", None))
    if fn and "Status" in df.columns:
        styler = fn(_status_color, subset=["Status"])

    right = [c for c in ["Trading Days", "Latest Close", "Period High", "Period Low"]
             if c in df.columns]
    left  = [c for c in ["Ticker", "Status", "Date Range"] if c in df.columns]
    if right: styler = styler.set_properties(**{"text-align": "right"}, subset=right)
    if left:  styler = styler.set_properties(**{"text-align": "left"},  subset=left)
    return styler
