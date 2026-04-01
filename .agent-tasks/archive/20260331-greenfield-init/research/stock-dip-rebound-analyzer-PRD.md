# PRD: Stock Dip Rebound Analyzer

**Created:** 2026-03-31
**Status:** Draft

---

## 1. Overview

**Problem statement:**
A trader wants a repeatable way to evaluate stocks that frequently dip and rebound, rather than relying on gut feel. They need historical analysis that estimates how often a defined dip is followed by at least a 3% rebound.

**Solution summary:**
Build a Python command-line tool that ingests historical stock bars from Alpaca Market Data, detects dip events (for example, daily close drops of >= 5%), and measures whether a rebound target (default 3%) is reached within a configurable look-ahead window. The tool prints a concise console report with hit rate and confidence interval so the user can prioritize consistency over occasional large wins.

**Scale / context:**
Single-user local analysis tool for personal trading research. Initial scope is one symbol at a time from the command line.

---

## 2. Users & Roles

| Role | Description | Key permissions |
|------|-------------|-----------------|
| Trader (Primary User) | Individual analyst testing dip/rebound behavior on symbols of interest | Run analysis, configure thresholds/windows, inspect confidence metrics |

---

## 3. Core User Flows

1. **Run Symbol Analysis** — Trader runs CLI with symbol/date range and gets dip/rebound metrics in console.
2. **Tune Strategy Parameters** — Trader adjusts dip threshold, rebound target, and look-ahead window, then reruns analysis.
3. **Review Event-Level Evidence** — Trader views recent dip events and whether each hit the target rebound.
4. **Offline Backfill Analysis** — Trader runs the same logic on local CSV historical bars when API access is unavailable.

---

## 4. Data Entities

- **DailyBar** — OHLCV record for a symbol and date.
- **DipEvent** — A detected dip instance with entry price, max rebound during look-ahead, and success/failure outcome.
- **AnalysisReport** — Aggregate metrics from all dip events (hit rate, confidence interval, averages, sample size).

---

## 5. Features & Scope

### Must-have (MVP)

- Pull historical daily bars from Alpaca API for a given symbol and date range
- Detect dip events using configurable drop threshold (default 5%)
- Evaluate rebound success against configurable target (default 3%) within configurable window
- Print console report with:
  - total bars and dip events
  - success rate
  - confidence interval
  - average max rebound after dip
  - recent event outcomes
- Optional CSV input path using same analysis logic

### Nice-to-have (post-MVP)

- Multi-symbol batch scanning and ranking by consistency score
- Automatic weekly report export (CSV/JSON)
- Position-sizing and simple risk rules simulator

### Explicitly out of scope

- Live trading order execution
- Web UI/dashboard
- Real-time streaming analytics

---

## 6. Integrations & Constraints

**Third-party integrations:**
- Alpaca Market Data API (historical stock bars)

**Non-functional requirements:**
- Deterministic/reproducible analysis for same input parameters
- Clear CLI output and explicit handling for small sample sizes
- Secrets must come from environment variables, not hard-coded values

**Known constraints:**
- Market behavior can change over time; results are probabilistic, not guarantees
- API data availability and symbol support depend on Alpaca plan and market coverage

---

## 7. Open Questions

- [ ] Should the default dip trigger be based on previous close, intraday low, or both?
- [ ] What minimum dip sample size is acceptable before using a ticker for strategy decisions?
- [ ] Should confidence use Wilson interval only, or include Bayesian prior for sparse data?
