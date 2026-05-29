"""
Sidebar components — data freshness indicator and holdings editor.
Renders directly into the current Streamlit sidebar context.
"""
import streamlit as st
from datetime import date

from core.data  import TICKER_PRICE_DIR, save_holdings
from core.utils import ACCOUNT_OPTIONS, HOLDINGS_COLS, STALE_THRESHOLD_DAYS


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
            f"No price CSV in `data/ticker_price/`.\n\n"
            "Run `fetch_tickers.py` first."
        )


def render_holdings_editor(holdings) -> None:
    """
    Inline data_editor for adding/editing/removing positions.
    Includes Save and Export buttons. Call inside a `with st.sidebar:` block.
    """
    existing_pfs = sorted(
        {str(p) for p in holdings["portfolio"].dropna()
         if str(p).strip() and str(p) != "nan"}
    )
    pf_hint = ", ".join(existing_pfs) if existing_pfs else "e.g. Growth, Core"

    st.subheader("📋 Edit Positions")
    st.caption(
        "• **+** to add a row  •  🗑 to delete  •  Edit inline  \n"
        f"• **Portfolio** — current: `{pf_hint}`  \n"
        "• Blank portfolio → `Default`  \n"
        "• Click **Save** when done"
    )

    edited = st.data_editor(
        holdings,
        num_rows="dynamic",
        use_container_width=True,
        column_order=HOLDINGS_COLS,
        column_config={
            "ticker":        st.column_config.TextColumn(
                "Ticker", max_chars=15, help="Symbol e.g. NVDA, VTI"
            ),
            "shares":        st.column_config.NumberColumn(
                "Shares", min_value=0.00001, format="%.5f", step=0.00001,
                help="Fractional shares — min 0.00001"
            ),
            "avg_cost":      st.column_config.NumberColumn(
                "Avg Cost ($)", min_value=0.01, format="%.2f", step=0.01
            ),
            "purchase_date": st.column_config.DateColumn(
                "Buy Date", format="YYYY-MM-DD"
            ),
            "account":       st.column_config.SelectboxColumn(
                "Account", options=ACCOUNT_OPTIONS
            ),
            "portfolio":     st.column_config.TextColumn(
                "Portfolio", max_chars=30,
                help="Groups positions into separate tabs. Blank → 'Default'."
            ),
            "notes":         st.column_config.TextColumn("Notes"),
        },
        key="holdings_editor",
    )

    col_save, col_dl = st.columns(2)
    saved = False

    with col_save:
        if st.button("💾 Save", use_container_width=True, type="primary"):
            clean = edited.copy()
            clean["ticker"] = clean["ticker"].astype(str).str.strip().str.upper()
            clean["portfolio"] = (
                clean["portfolio"].fillna("").astype(str).str.strip()
                .replace("", "Default")
            )
            clean = clean[
                clean["ticker"].notna()
                & (clean["ticker"].str.len() > 0)
                & (clean["ticker"] != "NAN")
            ]
            save_holdings(clean)
            st.cache_data.clear()
            st.success("✅ Saved!")
            saved = True

    with col_dl:
        st.download_button(
            "⬇ Export",
            data=holdings.to_csv(index=False).encode(),
            file_name="holdings.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if saved:
        st.rerun()
