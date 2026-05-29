"""
Shared constants, format helpers, and pandas Styler functions.
No Streamlit imports — safe to use in tests and non-UI contexts.
"""
import pandas as pd
import plotly.express as px

# ── Constants ─────────────────────────────────────────────────────────────────
ACCOUNT_OPTIONS = ["Brokerage", "IRA", "Roth IRA", "401k", "ESPP", "Other"]

# Trade log schema — matches data/trade_log.csv and core/holdings.py
TRADE_LOG_COLS = [
    "date", "ticker", "action", "shares", "price_per_share",
    "fees", "portfolio", "account", "notes",
]

STALE_THRESHOLD_DAYS = 3
PALETTE = px.colors.qualitative.Pastel   # stable cross-chart palette

# ── Currency support ──────────────────────────────────────────────────────────

CURRENCIES = {
    "USD": {"symbol": "$",   "decimals": 2, "name": "US Dollar"},
    "THB": {"symbol": "฿",   "decimals": 2, "name": "Thai Baht"},
    "JPY": {"symbol": "¥",   "decimals": 0, "name": "Japanese Yen"},
    "HKD": {"symbol": "HK$", "decimals": 2, "name": "Hong Kong Dollar"},
}


def make_cx(code: str, fx_rates: dict) -> dict:
    """
    Build a currency-context dict from a code and a rates lookup.

    Returned dict:
        code      – "USD" / "THB" / "JPY" / "HKD"
        symbol    – "฿" etc.
        decimals  – 0 for JPY, 2 for others
        name      – full currency name
        rate      – multiplier to apply to USD amounts before display
    """
    info = CURRENCIES.get(code, CURRENCIES["USD"])
    return {
        "code":     code,
        "symbol":   info["symbol"],
        "decimals": info["decimals"],
        "name":     info["name"],
        "rate":     float(fx_rates.get(code) or 1.0),
    }


DEFAULT_CX = make_cx("USD", {"USD": 1.0})   # fallback when no cx is passed


# ── Format helpers (USD-fixed — used outside styled tables) ───────────────────
SHARES_FMT = lambda v: f"{v:,.5f}".rstrip("0").rstrip(".") if pd.notna(v) else "—"
PL_P_FMT   = lambda v: f"{v:+.2f}%" if pd.notna(v) else "—"


def _cx_formatters(cx: dict):
    """
    Return (money, money_signed) callables that convert USD → cx currency.

    money(v)        → "฿36,500.00"  or  "¥5,432"
    money_signed(v) → "+฿1,234.56"  or  "-¥500"
    The sign is placed BEFORE the symbol so Streamlit metric delta colouring works.
    """
    sym  = cx["symbol"]
    dec  = cx["decimals"]
    rate = cx["rate"]

    def money(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        c = v * rate
        return f"{sym}{c:,.{dec}f}" if dec > 0 else f"{sym}{c:,.0f}"

    def money_signed(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        c = v * rate
        s = "+" if c >= 0 else "-"
        a = abs(c)
        return f"{s}{sym}{a:,.{dec}f}" if dec > 0 else f"{s}{sym}{a:,.0f}"

    return money, money_signed


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

def style_holdings_table(
    df: pd.DataFrame,
    show_portfolio: bool = False,
    cx: dict | None = None,
):
    """Style the main per-ticker holdings table, converting values to cx currency."""
    cx = cx or DEFAULT_CX
    _m, _ms = _cx_formatters(cx)

    col_order = ["Portfolio", "Ticker", "Lots", "Shares", "Avg Cost", "Current Price",
                 "Cost Basis", "Market Value", "P/L $", "P/L %", "Account(s)"]
    if not show_portfolio:
        col_order = [c for c in col_order if c != "Portfolio"]
    display_cols = [c for c in col_order if c in df.columns]
    display = df[display_cols].copy()

    fmt = {
        "Lots":          "{:,d}",
        "Shares":        SHARES_FMT,
        "Avg Cost":      _m,
        "Current Price": lambda v: _m(v) if pd.notna(v) else "—",
        "Cost Basis":    _m,
        "Market Value":  lambda v: _m(v) if pd.notna(v) else "—",
        "P/L $":         lambda v: _ms(v) if pd.notna(v) else "—",
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


def style_portfolio_summary(df: pd.DataFrame, cx: dict | None = None):
    """Style the per-portfolio rollup table."""
    cx = cx or DEFAULT_CX
    _m, _ms = _cx_formatters(cx)

    fmt = {
        "Positions":    "{:,d}",
        "Cost Basis":   _m,
        "Market Value": lambda v: _m(v) if pd.notna(v) else "—",
        "P/L $":        lambda v: _ms(v) if pd.notna(v) else "—",
        "P/L %":        PL_P_FMT,
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styler = df.style.format(fmt, na_rep="—")
    return apply_pl_color(styler, ["P/L $", "P/L %"])


def style_market_summary(df: pd.DataFrame):
    """Style the market-data ticker summary table (always USD — no cx needed)."""
    def _opt(v):
        return f"${v:,.2f}" if pd.notna(v) else "—"

    fmt = {
        "Latest Close": _opt,
        "Period High":  _opt,
        "Period Low":   _opt,
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
