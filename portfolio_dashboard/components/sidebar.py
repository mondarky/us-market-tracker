"""
Sidebar components — data freshness indicator and trade log editor.
Renders directly into the current Streamlit sidebar context.
"""
import streamlit as st
from datetime import date

from core.data  import TICKER_PRICE_DIR, save_trade_log
from core.utils import ACCOUNT_OPTIONS, TRADE_LOG_COLS, STALE_THRESHOLD_DAYS, CURRENCIES, make_cx


def render_data_freshness(price_file: str | None, price_date) -> None:
    """Show the price CSV freshness badge. Call inside a `with st.sidebar:` block."""
    st.subheader("📂 Price Data Source")
    if price_file:
        st.caption(f"`{price_file}`")
        if price_date:
            gap = (date.today() - price_date).days
            if gap <= STALE_THRESHOLD_DAYS:
                st.success(f"✅ Fresh — {price_date}")
            else:
                st.warning(
                    f"⚠️ Stale — {gap} days old ({price_date})\n\n"
                    f"Re-run `fetch_tickers.py` in `ticker_fetcher/`"
                )
    else:
        st.error(
            "No price CSV in `data/ticker_price/`.\n\n"
            "Run `fetch_tickers.py` first."
        )


def render_trade_log_editor(trade_log) -> None:
    """
    Inline data_editor for the trade log — add / edit / delete BUY and SELL rows.
    Open positions are always derived automatically from the full log.
    Call inside a `with st.sidebar:` block.
    """
    import pandas as pd

    # Drop the derived column before display — it's read-only
    display_df = trade_log.drop(columns=["signed_shares"], errors="ignore").copy()

    # DateColumn requires datetime.date objects, not Timestamps
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(
            display_df["date"], errors="coerce"
        ).dt.date

    # Current portfolio names for the hint
    existing_pfs = sorted(
        {str(p) for p in display_df["portfolio"].dropna()
         if str(p).strip() and str(p) not in ("nan", "Default")}
    )
    pf_hint = ", ".join(existing_pfs) if existing_pfs else "e.g. Growth, Speculative"

    st.subheader("📋 Trade Log")
    st.caption(
        "• **+** to add a row  •  🗑 to delete  •  Edit inline  \n"
        f"• **Portfolio** — current: `{pf_hint}`  \n"
        "• Positions are derived automatically from BUY / SELL history  \n"
        "• Click **Save** when done"
    )

    edited = st.data_editor(
        display_df,
        num_rows="dynamic",
        use_container_width=True,
        column_order=TRADE_LOG_COLS,
        column_config={
            "date":            st.column_config.DateColumn(
                "Date", format="YYYY-MM-DD", help="Trade execution date"
            ),
            "ticker":          st.column_config.TextColumn(
                "Ticker", max_chars=15, help="Symbol e.g. NVDA, VTI"
            ),
            "action":          st.column_config.SelectboxColumn(
                "Action", options=["BUY", "SELL"],
                help="BUY to open / add; SELL to close / reduce"
            ),
            "shares":          st.column_config.NumberColumn(
                "Shares", min_value=0.00001, format="%.5f", step=0.00001,
                help="Number of shares — always positive"
            ),
            "price_per_share": st.column_config.NumberColumn(
                "Price/Share ($)", min_value=0.01, format="%.4f", step=0.01,
                help="Execution price per share before fees"
            ),
            "fees":            st.column_config.NumberColumn(
                "Fees ($)", min_value=0.0, format="%.2f", step=0.01,
                help="Brokerage commission — 0 if none"
            ),
            "portfolio":       st.column_config.TextColumn(
                "Portfolio", max_chars=30,
                help="Groups positions into separate tabs. Blank → 'Default'."
            ),
            "account":         st.column_config.SelectboxColumn(
                "Account", options=ACCOUNT_OPTIONS
            ),
            "notes":           st.column_config.TextColumn("Notes"),
        },
        key="trade_log_editor",
    )

    col_save, col_dl = st.columns(2)
    saved = False

    with col_save:
        if st.button("💾 Save", use_container_width=True, type="primary"):
            clean = edited.copy()
            # Normalise key fields
            clean["ticker"]    = clean["ticker"].astype(str).str.strip().str.upper()
            clean["action"]    = clean["action"].astype(str).str.strip().str.upper()
            clean["portfolio"] = (
                clean["portfolio"].fillna("").astype(str).str.strip()
                .replace("", "Default")
            )
            # Drop rows with no ticker or no valid action
            clean = clean[
                clean["ticker"].notna()
                & (clean["ticker"].str.len() > 0)
                & (clean["ticker"] != "NAN")
                & clean["action"].isin(["BUY", "SELL"])
            ]
            save_trade_log(clean)
            st.cache_data.clear()
            st.success("✅ Saved!")
            saved = True

    with col_dl:
        st.download_button(
            "⬇ Export",
            data=display_df.to_csv(index=False).encode(),
            file_name="trade_log.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if saved:
        st.rerun()


def render_currency_selector(
    fx_rates: dict,
    currencies_dict: dict | None = None,
) -> dict:
    """
    Render a currency dropdown.
    currencies_dict: from load_fx_config() — drives the label and metadata.
                     Falls back to CURRENCIES (hardcoded) if None.
    Only shows currencies whose rate was successfully fetched.
    Sets st.session_state["display_currency"] and returns the cx dict.
    Call inside a `with st.sidebar:` block.
    """
    lookup    = currencies_dict if currencies_dict is not None else CURRENCIES
    available = ["USD"] + [c for c in lookup if c != "USD"
                           and fx_rates.get(c) is not None]

    selected = st.selectbox(
        "💱 Display currency",
        options=available,
        format_func=lambda c: (
            f"{lookup[c]['symbol']} {c} — {lookup[c]['name']}"
            if c in lookup else c
        ),
        key="display_currency",
    )

    cx = make_cx(selected, fx_rates, currencies_dict=currencies_dict)

    if selected != "USD":
        rate = cx["rate"]
        dec  = cx["decimals"]
        fmt  = f"{rate:,.{dec}f}" if dec > 0 else f"{rate:,.0f}"
        st.caption(f"Rate: 1 USD = {fmt} {selected}")

    return cx
