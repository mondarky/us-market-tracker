# US Market Tracker

A personal investment portfolio dashboard built with Streamlit, Python, and yfinance.  
Tracks unrealised P/L, portfolio performance over time, and market data for a custom watchlist.

---

## Features

| Page | Description |
|---|---|
| **Portfolio** | Unrealised P/L per holding with FIFO cost basis. Supports multiple named portfolios, fractional shares (min 0.00001), and multi-lot positions. |
| **Market Data** | Candlestick charts for every ticker in the watchlist. Search and sort by price, range, or trading days. |
| **Performance** | Portfolio value over time, running P/L curve, and best/worst week callouts. History grows automatically as more price fetches accumulate. |

**Other highlights:**
- Trade log data model — BUY/SELL history replaces a static holdings snapshot; open positions and cost basis are derived via FIFO
- Multi-portfolio tabs (e.g. *Growth ETFs*, *Speculative*)
- Price CSV stitching — all fetched CSVs are merged for maximum history depth
- Sidebar trade log editor — add, edit, or remove trades inline
- Stale/short-history flags on fetched tickers

---

## Tech Stack

| Tool | Purpose |
|---|---|
| [Streamlit](https://streamlit.io/) | Multi-page web UI |
| [yfinance](https://github.com/ranaroussi/yfinance) | Market data fetching |
| [Plotly](https://plotly.com/python/) | Interactive charts |
| [pandas](https://pandas.pydata.org/) | Data processing and FIFO calculations |
| Python 3.12+ | Runtime |

---

## Project Structure

```
us-market-tracker/
│
├── ticker_fetcher/
│   ├── fetch_tickers.py        # Fetch OHLCV data via yfinance; outputs to data/ticker_price/
│   └── tickers.txt             # Watchlist — one symbol per line
│
└── portfolio_dashboard/
    ├── app.py                  # Home page & Streamlit entry point
    ├── requirements.txt
    │
    ├── pages/
    │   ├── 1_Portfolio.py      # P/L dashboard
    │   ├── 2_Market_Data.py    # Candlestick chart browser
    │   └── 3_Performance.py    # Value over time & weekly callouts
    │
    ├── core/                   # Shared logic — no Streamlit
    │   ├── holdings.py         # Trade log I/O, FIFO engine, performance series
    │   ├── data.py             # File loading with @st.cache_data
    │   ├── analysis.py         # Portfolio aggregation, weekly performance
    │   └── utils.py            # Constants, formatters, Styler functions
    │
    ├── components/             # Reusable Streamlit widgets
    │   ├── charts.py           # All Plotly chart renderers
    │   └── sidebar.py          # Data freshness indicator, trade log editor
    │
    └── data/                   # Local storage — gitignored (see below)
        ├── trade_log.csv       # Personal trade history (BUY/SELL ledger)
        ├── holdings/           # Legacy holdings snapshot
        └── ticker_price/       # Fetched price CSVs (auto-generated)
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/mondarky/us-market-tracker.git
cd us-market-tracker
```

### 2. Install dependencies

```bash
pip install -r portfolio_dashboard/requirements.txt
```

### 3. Configure your watchlist

Edit `ticker_fetcher/tickers.txt` — one ticker symbol per line:

```
NVDA
VTI
AAPL
# lines starting with # are ignored
```

### 4. Fetch initial price data

```bash
python ticker_fetcher/fetch_tickers.py
```

This creates `portfolio_dashboard/data/ticker_price/ticker_data_YYYYMMDD.csv`.  
Run it regularly (daily or weekly) to grow your performance history.

> **Tip:** Change `PERIOD` in `fetch_tickers.py` to `"3mo"`, `"6mo"`, or `"1y"` for more history on the first fetch.

### 5. Add your holdings

Run the app and use the **Portfolio page sidebar** to log your trades:

```bash
streamlit run portfolio_dashboard/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Trade Log Format

All positions are derived from `data/trade_log.csv`.  
Edit via the sidebar in the app, or directly in the CSV:

```
date,ticker,action,shares,price_per_share,fees,portfolio,account,notes
2026-05-21,NVDA,BUY,3.0,188.12,0.00,Speculative,Brokerage,initial buy
2026-06-01,VTI,BUY,6.5,361.00,0.00,Growth ETFs,IRA,
```

| Column | Required | Notes |
|---|---|---|
| `date` | Yes | YYYY-MM-DD — actual trade/settlement date |
| `ticker` | Yes | Must match yfinance symbol exactly |
| `action` | Yes | `BUY` or `SELL` |
| `shares` | Yes | Always positive; fractional shares supported |
| `price_per_share` | Yes | Execution price before fees |
| `fees` | No | Brokerage commission — default `0.0` |
| `portfolio` | Yes | Groups positions into separate tabs |
| `account` | Yes | e.g. `Brokerage`, `IRA`, `ESPP` |
| `notes` | No | Free text |

Cost basis and open positions are calculated automatically via **FIFO lot matching**.

---

## Data & Privacy

The following are excluded from version control (see `.gitignore`):

| Path | Reason |
|---|---|
| `data/trade_log.csv` | Personal trade history |
| `data/holdings/` | Legacy holdings snapshot |
| `data/ticker_price/*.csv` | Regeneratable — run `fetch_tickers.py` |

**Keep `trade_log.csv` backed up separately** (e.g. encrypted cloud storage).

---

## New PC Setup

```bash
git clone https://github.com/mondarky/us-market-tracker.git
cd us-market-tracker
pip install -r portfolio_dashboard/requirements.txt

# Restore personal data from your secure backup:
cp /path/to/backup/trade_log.csv portfolio_dashboard/data/trade_log.csv

# Regenerate price history:
python ticker_fetcher/fetch_tickers.py

# Launch:
streamlit run portfolio_dashboard/app.py
```

---

## License

Personal project — not licensed for redistribution.
