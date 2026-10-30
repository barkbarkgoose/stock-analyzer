# Dipwork — Stock Dip/Rebound Research Workbench

A single-purpose research tool for one question:

> **For a volatile stock in an uptrend, after a >=5% dip, when can we confirm that the rebound has actually started — and how often does +1% get hit before the stop, within one or two trading days?**

Dipwork is not a trading bot and does not place orders. It builds a **profile** for a symbol: a plain-English **strategy** for that stock (when to watch, when to buy, when to sell), how far its dips actually bounce, and — kept separate — what would have happened if you had followed the strategy **blind**, day by day, without knowing the future.

---

## The buy-signal thesis

The dip itself is **not** the buy signal. The dangerous pattern is:

```
drop 5%  →  bounce 1-2%  →  make a lower low  →  finally recover
```

Dipwork models that sequence explicitly.

1. **Uptrend filter** — price above/near SMA50, SMA50 above SMA200, price above SMA200, positive 6-month return, controlled 1-year drawdown, not over-extended.
2. **Volatility filter** — enough 5% intraday range days and/or ATR, plus liquidity.
3. **Multi-leg dip episode** — a 5% drawdown starts an episode. A bounce followed by a new low does **not** start a fresh episode; it increments the failed-bounce / attempt count. For bookkeeping the episode ends on a close above the pre-dip reference high or after a maximum duration — but trading never waits for a full recovery: buys stop at the **bounce cutoff** and every trade sells at its own target. This is how fake rebounds become a feature instead of a surprise.
4. **Bounce cutoff (watch window)** — the stock is in *watch* while it is in a dip and has not yet bounced past the cutoff, measured from the dip's own low. Past it the stock is *extended*: the easy part of the bounce is gone. In `auto` mode the cutoff is learned per stock: the bounce that 3 in 4 past dips reached, minus the target. The profile shows the full "how far do dips bounce" table.
5. **Confirmation rules** — higher low, swing-high reclaim, 9-EMA reclaim, session VWAP reclaim, volume expansion, RSI reclaim, and composites. The baseline is “buy every dip bar”, so every confirmation has to beat it.
6. **Triple-barrier labels** — enter at the **next bar’s open**, target `+1%`, stop `-2%` (configurable or structure-based), max hold `2 trading days`. If target and stop are both inside one bar, the stop is assumed first. Slippage and commission are included.
7. **Blind simulation** — walks forward one session at a time. Each morning it picks the buy rule (best net-positive record among trades that had already *closed*) and the bounce cutoff (from dips that had already *finished*), then trades that day, one position at a time. It sits out when no rule has earned trust yet. It re-runs at several targets (+1/1.5/2/2.5%) so you can see whether a higher target is realistic for a stock. A test proves that cutting off future bars never changes an earlier decision. This replaces the old fold-based rule walk-forward.
8. **Probability model** — a small L2 logistic regression estimates `P(target before stop)` and a separate fast-horizon model estimates `P(hit within the next 2 hours)`. Features include the dip-episode state, confirmation quality, volatility/time-of-day, and the prior day / two-day return and range from completed daily bars. It is deliberately transparent, with coefficients, calibration and walk-forward folds in the UI. The probability cutoff is selected on the first 60% of walk-forward OOS predictions and evaluated on the held-out 40%. If there are not enough samples, it says so instead of pretending.

The profile reports both **signal-level** statistics (all raw signals) and **sequential trade** statistics (one position at a time). Headline metrics use sequential trades; the conditional tables use all signals so you can see the attempt/depth/time-of-day splits.

---

## What the workbench shows

- **Strategy card** — the per-stock playbook in four steps (watch → stop watching → buy → sell), each with a live ✓/✗ checklist against the latest bar, the blind track record, and a per-stock target picker. If no rule has a net-positive record the card says *sit out* and the paper trader will not trade it.
- **Blind simulation tab** — blind trades, equity curve, the daily decisions it made, the gap to hindsight, and the target ladder.
- **What actually happened tab** — the true history, labelled as hindsight: bounce profile, every dip that happened, the rule comparison, fake-rebound and attempt studies, the model.
- **Automation readiness** — a plain-language verdict: promising / fragile / needs more data / no demonstrated edge / not qualified, with the exact OOS, fake-rebound, time-in-market and model evidence behind it.
- **Verdict** — qualified / watch / reject, score, every qualification check.
- **Current read** — active dip episode, attempt number, failed bounces, off-the-low run-up, waiting-for list, fake-rebound risk, entry/target/stop levels, model probabilities.
- **Price chart** — candles, volume, shaded *watch* / *extended* periods, and buy/target/stop markers from either the blind simulation or the hindsight rule.
- **Rule comparison** — trades, hit rate + Wilson CI, net EV/trade, weekly return, trades/week, stop rate, fast-horizon hit rate, median time in market, max drawdown, rank score. Click a rule for attempt/depth/time/run-up splits.
- **Fake-rebound study** — baseline first attempt vs confirmed first attempt, and baseline vs confirmed after a failed bounce.
- **Attempt analysis** — first vs second vs third+ attempt, and no-failed-bounce vs failed-bounce splits.
- **Model panel** — AUC, Brier, calibration bins, threshold curve, feature coefficients, model-filter vs unfiltered OOS, walk-forward folds.
- **Trade log and equity curve** — sequential simulated trades with per-trade probability, attempt, failed bounces, run-up, dip depth, MFE/MAE.
- **Data coverage** — what is cached, from which provider, how many sessions, and the exact warnings.

The **Screener** is daily-first: it scans a universe for trend, liquidity, 5% range days and dip frequency, then optionally builds full intraday profiles for qualifiers. The intraday run adds the same readiness verdict, so you can sort candidates by demonstrated OOS edge rather than just trend score. The **Watchlist** keeps live reads and paper trades. Live data is polled on demand (live check / paper tick), not streamed; run `python manage.py paper_tick --interval 60` for a loop. The **Paper** page is a deterministic simulator, not a broker integration. When the profile enables the probability filter, the paper trader applies the same threshold before opening a trade.

---

## Data sources and the cache

The cache is a core design choice. Yahoo will not serve 5-minute bars older than ~60 days, so Dipwork keeps every bar it has ever fetched. Re-running an analysis only asks the provider for ranges that are not already covered. Running the backfill command periodically accumulates a much longer 5-minute history than any free provider serves in one request. After the cache has accumulated, raise `intraday_history_days` in the study config to use it — the provider limit only affects fetching, not reading cached bars.

| Provider | Good for | Limits / caveats |
|---|---|---|
| **Yahoo** (default) | Free daily history + recent intraday | ~6 usable days of 1m, ~58 usable days of 5m/15m/30m, ~720 days of 1h. Unofficial; be polite. |
| **Alpaca** | Multi-month intraday | Free plans are usually **IEX-only**; volume/spread data is not consolidated. `ALPACA_FEED=sip` if your plan has it. |
| **CSV** | Your own data | Date/timestamp + OHLCV columns; directory mode supports `SYMBOL.csv`. |
| **Synthetic** | Offline demo/test | `DEMO`, `SYNTH-UP`, `SYNTH-FAKE`, `SYNTH-CLEAN`, `SYNTH-CHOP`, `SYNTH-DOWN`, `SYNTH-QUIET`. Not real data. |

Cache rules:

- Bars are unique by `(security, timeframe, timestamp)` and upserted.
- A provider change (including synthetic → real, or Alpaca IEX → SIP) **resets that symbol/timeframe cache** so sources are never mixed. Cached profiles are keyed by `(config hash, source, data version)` and are invalidated when data or source changes.
- `DataCoverage` stores the earliest/latest cached timestamp and the provider’s “unavailable before” boundary.
- `FetchLog` records every provider request so you can see exactly what was fetched.
- Yahoo’s provider limit is clamped to 58 days for 5m (not 60) because Yahoo rejects a full 60-day window at the boundary.

### Rate limits (and why not Robinhood)

- **Yahoo** has no official rate-limit contract. The client throttles to 4 requests/second, backs off on errors, and avoids re-fetching cached ranges. The real constraint is intraday depth, not request rate.
- **Alpaca** documents roughly 200 requests/minute; the client targets 180/minute, paginates, and retries 429s.
- **Robinhood** has no supported public market-data API for this workflow. Using private endpoints would be brittle and ToS-risky, so Dipwork does not use it. There is no broker connection anywhere in the project.

### Accumulating intraday history

```bash
# Run daily/weekly via cron. Add symbols, or use --watchlist.
cd backend
uv run python manage.py backfill_intraday --symbols TSLA,NVDA,AMD --days 60
uv run python manage.py backfill_intraday --watchlist
```

---

## Setup

Prerequisites: Python 3.12/3.13, [`uv`](https://docs.astral.sh/uv/), Node 20+, and a package manager for the frontend. The repo is set up for pnpm; a local `node_modules` is the only hard requirement for `./dev.sh`.

```bash
# 1. Python environment
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt

# 2. Backend env
cp backend/.env.example backend/.env
# Edit backend/.env. At minimum set SECRET_KEY. ./dev.sh can generate one.

# 3. Frontend deps
cd frontend
npx -y pnpm@11.13.0 install
# or: npm install
cd ..

# 4. Run both servers
./dev.sh
```

The runner finds free ports starting at `8800` (Django) and `5177` (Vite), applies migrations, and stops both on Ctrl+C. Open `http://localhost:5177`. For production, build `frontend/dist`, serve it from any static host, and proxy `/api` to Django; the dev runner is development-only.

### Choosing a provider

```bash
# backend/.env
MARKET_PROVIDER=auto          # alpaca if keys exist, otherwise yahoo
# MARKET_PROVIDER=yahoo
# MARKET_PROVIDER=alpaca
# MARKET_PROVIDER=synthetic
# MARKET_PROVIDER=csv
# MARKET_CSV_PATH=/absolute/path/to/bars.csv

ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_FEED=iex               # or sip
ALPACA_ADJUSTMENT=all
```

The backend reads `backend/.env`, the OS environment, then the encrypted keychain (keychain values win). If you use the keychain, set `MARKET_PROVIDER` there so it does not get out of sync with `.env`.

### Demo without any market API

```bash
MARKET_PROVIDER=synthetic ./dev.sh
```

Then analyze `DEMO` or `SYNTH-FAKE`. The synthetic series is deterministic, has an uptrend, volatile dips, fake rebounds and clean rebounds. It is useful for validating the workflow, not for drawing market conclusions.

---

## CLI

All commands run from `backend/` and use the same cached data, providers and engine as the API.

```bash
cd backend

# Build and print a profile
uv run python manage.py analyze_symbol TSLA --timeframe 5m
uv run python manage.py analyze_symbol DEMO --timeframe 5m --json

# Force a provider refresh + rebuild
uv run python manage.py analyze_symbol TSLA --timeframe 5m --force

# Cache bars only
uv run python manage.py ingest_symbol TSLA --timeframe 5m --days 60

# Current signal without placing a paper trade
uv run python manage.py live_signal TSLA

# Screen the bundled universe (daily first)
uv run python manage.py screen_universe --limit 25 --with-intraday

# Seed / extend the universe
uv run python manage.py seed_universe

# Paper-trading loop (simulated only)
uv run python manage.py paper_tick --once
uv run python manage.py paper_tick --interval 60
```

The standalone engine CLI (no Django, no cache) also exists for quick checks:

```bash
uv run python -m stock_rebound_analyzer.cli DEMO --provider synthetic --timeframe 5m
uv run python -m stock_rebound_analyzer.cli AAPL --provider yahoo --timeframe 1d --json
```

---

## HTTP API

Market endpoints are intentionally `AllowAny` for local single-user use. If you expose the app beyond localhost, put it behind auth (or the existing JWT layer).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/market/config` | Defaults, config schema, provider info, caveats |
| GET | `/api/v1/market/symbols?q=` | Symbol search (universe + cache + direct symbol) |
| POST | `/api/v1/market/analyze` | Build/cached profile `{symbol, config, force, source}` |
| GET | `/api/v1/market/profile/<symbol>` | Latest cached profile |
| POST | `/api/v1/market/ingest` | Incremental bar fetch `{symbol, timeframe, start/end/days}` |
| GET | `/api/v1/market/coverage/<symbol>` | Coverage, provider, bar counts |
| GET | `/api/v1/market/chart/<symbol>` | OHLCV for the chart |
| GET | `/api/v1/market/watchlist` | Watchlist + open paper trade |
| POST | `/api/v1/market/watchlist` | Add `{symbol, note}` |
| DELETE | `/api/v1/market/watchlist/<symbol>` | Remove |
| POST | `/api/v1/market/live-check` | Current state, levels, probabilities |
| POST | `/api/v1/market/screen` | Start a screen run (poll by id) |
| GET | `/api/v1/market/screen/<id>` | Screen progress/results |
| POST | `/api/v1/market/paper/tick` | Run one simulated tick over the watchlist |
| GET | `/api/v1/market/paper/trades` | Paper trade history |
| GET | `/api/v1/market/paper/stats` | Aggregate paper stats |
| POST | `/api/v1/market/paper/trades/<id>/close` | Manual close |

Example:

```bash
curl -X POST http://127.0.0.1:8800/api/v1/market/analyze \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"TSLA","config":{"timeframe":"5m","dip_threshold_pct":5,"target_pct":1,"stop_pct":2,"max_hold_days":2}}'
```

---

## How to read the numbers

- **Hit rate** — target hit before stop, using sequential (non-overlapping) trades. The 95% interval is Wilson.
- **Net EV/trade** — average net return after slippage/commission. This, not hit rate, decides whether a rule is worth trading.
- **Weekly return** — compounded sequential return over the data window, annualised to a week. It is a sample estimate, not a forecast.
- **Trades/week** — how often the rule actually traded inside the window.
- **Median hold** — market minutes in the trade, excluding overnight gaps. This is the “minimal time in market” metric.
- **Fast hit rate** — share of trades that hit target within the fast horizon (default 2 hours on 5m).
- **Blind simulation** — the strategy traded with no knowledge of the future. This is the number to trust most. The readiness verdict requires it to be net positive with a hit-rate interval above 50% before calling a setup promising. The rule table and hindsight trade log pick the best rule after seeing everything, so they flatter; the gap between the two is the cost of not knowing the future.
- **Break-even hit rate** — the win rate needed just to not lose money at a given target and stop, after costs (~70% for +1%/-2%, ~53% for +2%/-2%).
- **Model AUC / Brier** — ranking quality and calibration. AUC near 0.5 means the model adds little; Brier near the base rate means it is not calibrated.
- **No recommended rule** — if no confirmation rule produced the minimum number of sequential trades, the profile deliberately shows no recommendation. The rule table is still there for exploration, but the tool will not pretend it found an edge.
- **Fake-rebound study** — compares buying the raw first attempt with buying a confirmed first attempt. If confirmation does not improve the first-attempt hit rate in your sample, the tool says so.

### A note on the 1% target / 2% stop

With a `+1%` target and `-2%` stop, you need a high hit rate to break even. That is intentional: the default is a consistency-first configuration, not an optimal one. Use the stop/stop-mode/max-hold controls to compare. A structure stop below the episode low can make sense for a deep dip, but it also increases per-trade risk. The profile shows you both sides (net EV, stop rate, max drawdown, time in market) rather than hiding the trade-off in a single score.

---

## Repo structure

```
stock_rebound_analyzer/     Pure Python research engine
  providers/                Yahoo, Alpaca, CSV, synthetic
  features.py               Causal features + multi-leg dip tracker
  rules.py                  Confirmation rule registry
  labels.py                 Triple-barrier labels (next-open entry, stop-first)
  backtest.py               Sequential trade simulation
  bounces.py                Bounce profile + per-stock bounce cutoff
  blind.py                  Blind day-by-day replay, target ladder, watch bands
  model.py                  Logistic probability model + walk-forward
  profile.py                The profile JSON consumed by the UI/API
backend/apps/market/        Django persistence, ingestion, API, paper trading
frontend/src/               Vue 3 workbench (analyzer, screener, watchlist, paper)
tests/                      Engine unit tests
backend/apps/market/tests/  API/service tests
```

---

## Tests

```bash
# Engine (no Django)
.venv/bin/python -m pytest tests -q

# Backend (Django test DB + synthetic provider)
cd backend && ../.venv/bin/python -m pytest -q

# Frontend typecheck + production build
cd frontend && npx -y pnpm@11.13.0 run build
```

The engine tests cover causality (truncating future bars does not change earlier rows), multi-leg episode tracking, stop-first labelling, Wilson intervals, AUC, calibration and a deterministic end-to-end profile. The API tests cover incremental cache behaviour, provider isolation, analysis caching, watchlist CRUD, live checks, screening and paper ticks.

---

## Limits and honest caveats

- **Historical research only.** Past behaviour does not guarantee future results. Nothing here is financial advice.
- **Free intraday data is short.** Yahoo’s 5m window is ~58 usable days. A 60-day profile is a small sample; use the blind simulation and confidence intervals, not a single hit rate. Picking a target from the ladder by eye is itself a little hindsight.
- **IEX is not consolidated.** Alpaca free-tier volume/spread conclusions are approximate.
- **Adjusted data.** Yahoo uses auto-adjusted OHLC; Alpaca uses the configured adjustment. Splits/dividends can differ across providers, which is why switching sources resets the cache.
- **Execution assumptions.** Next-bar-open entry, configured slippage, stop-first on ambiguous bars, one position at a time, no borrow/shorting, no taxes. Paper fills are simulated at the latest close + slippage.
- **Survivorship / universe.** The bundled universe is a convenience list, not a point-in-time index membership file.
- **Model overfitting.** The model uses a small feature set, L2 regularisation, an outcome embargo and walk-forward validation, but a few hundred correlated signals per symbol is still a small sample. The UI reports when the model is unavailable or weak.
