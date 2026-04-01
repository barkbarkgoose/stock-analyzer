# Stock Dip Rebound Analyzer

Simple Python CLI for analyzing historical dip-and-rebound behavior using configurable market data providers (Yahoo Finance, Alpaca, or CSV).

## What It Measures

For each dip event (default: daily close drops by 5% or more from previous close), the analyzer checks whether price rebounds by at least 3% within the next N trading days (default: 5).

It reports:
- Number of dip events
- Success count/rate
- Wilson 95% confidence interval for success probability
- Average max rebound and average worst drawdown after entry
- Recent dip event outcomes

## Setup

1. Create a virtual environment and install dependencies:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

2. (Optional) Create `.env` from `.env.example` for data providers that require API keys.

3. Set `DATA_SOURCE` environment variable to choose data provider:
   - `yahoo` (default) - Free, uses Yahoo Finance
   - `alpaca` - Requires ALPACA_API_KEY and ALPACA_API_SECRET in `.env`
   - `csv` - Use `--csv` flag instead

## Usage

Analyze using Yahoo Finance (default, free):

```bash
uv run python -m stock_rebound_analyzer.cli \
  --symbol SUUN \
  --start 2025-01-01 \
  --end 2026-03-31 \
  --dip-threshold 5 \
  --rebound-target 3 \
  --rebound-window 5
```

Analyze using Alpaca API (set DATA_SOURCE=alpaca in .env):

```bash
DATA_SOURCE=alpaca uv run python -m stock_rebound_analyzer.cli \
  --symbol SUUN \
  --start 2025-01-01 \
  --end 2026-03-31
```

Analyze from local CSV (columns: date,open,high,low,close,volume and optional symbol):

```bash
uv run python -m stock_rebound_analyzer.cli \
  --symbol SUUN \
  --csv ./data/suun_daily.csv
```

## Notes

- This is statistical research, not trading advice.
- A high hit rate in historical data does not guarantee future performance.
- For very small sample sizes, confidence intervals will be wide.
