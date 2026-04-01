# Project Blueprint: Stock Dip Rebound Analyzer

**Created:** 2026-03-31
**Status:** Draft
**Stack:** Python CLI / No frontend / Alpaca Market Data API

---

## 1. Overview

This project is a Python-first command-line analysis tool for identifying recurring dip-and-rebound patterns in stocks. The primary use case is a trader who wants to evaluate whether buying dips has historically delivered a reliable short-term rebound, with consistency prioritized over large one-off wins.

The system ingests historical OHLCV stock bars from Alpaca, detects dip events using configurable rules (for example, >= 5% close-to-close drops), and measures whether each dip is followed by a rebound target (default 3%) within a configurable number of trading days.

The output is console-based and intentionally minimal: aggregate strategy statistics, confidence bounds, and event-level evidence. This keeps the first version fast to build and easy to iterate.

## 2. Requirements

### Functional Requirements

- [FR-01] User can run analysis for a symbol and date range from CLI.
- [FR-02] System fetches historical daily bars from Alpaca using API credentials from environment variables.
- [FR-03] User can configure dip threshold %, rebound target %, and rebound window (days).
- [FR-04] System detects dip events and computes per-event success/failure of hitting rebound target.
- [FR-05] System prints aggregate metrics: sample size, success rate, confidence interval, and average returns.
- [FR-06] System can optionally read local CSV bars and run the same analysis logic.

### Non-Functional Requirements

- [NFR-01] Deterministic output for identical input data and parameters.
- [NFR-02] CLI execution should complete quickly for 1-2 years of daily data per symbol.
- [NFR-03] Credentials and secrets must not be committed to source control.
- [NFR-04] Logic for statistical calculations must be covered by automated tests.

### Assumptions

- Initial user is a single local operator (no multi-user auth needed).
- Daily bars are sufficient for v1; intraday data is deferred.
- No order execution is required in v1.

### Out of Scope

- Web UI or dashboard
- Broker order routing/execution
- Real-time market streaming
- Portfolio-level strategy optimization

## 3. Tech Stack

| Layer | Choice | Deviation from default? |
|-------|--------|------------------------|
| Runtime | Python 3.x | Yes (no Django needed for CLI-only v1) |
| Framework | None (stdlib + requests) | Yes |
| Data Source | Alpaca Market Data REST API | Yes |
| Testing | unittest (stdlib) | Yes |
| Frontend | None | Yes |
| Database | None (in-memory analysis) | Yes |

Deviations are intentional because v1 is console-only and does not require a web/API server.

## 4. Data Model

### Entities

#### DailyBar

| Field | Type | Constraints |
|-------|------|-------------|
| symbol | str | required |
| date | date | required |
| open | float | > 0 |
| high | float | >= low |
| low | float | > 0 |
| close | float | > 0 |
| volume | int | >= 0 |

**Relationships:**
- Belongs to one symbol/time-series.

#### DipEvent

| Field | Type | Constraints |
|-------|------|-------------|
| date | date | required |
| dip_pct | float | >= dip_threshold |
| entry_price | float | > 0 |
| max_return_pct | float | any real |
| success | bool | required |
| days_to_target | int \| null | null when target not hit |

**Relationships:**
- Derived from a DailyBar at dip index plus forward look-ahead bars.

#### AnalysisReport

| Field | Type | Constraints |
|-------|------|-------------|
| symbol | str | required |
| bar_count | int | >= 0 |
| dip_count | int | >= 0 |
| success_count | int | 0..dip_count |
| success_rate | float | 0..1 |
| confidence_low | float | 0..1 |
| confidence_high | float | 0..1 |
| average_max_return_pct | float | any real |
| average_worst_drawdown_pct | float | <= 0 typically |

**Relationships:**
- Aggregate of many DipEvent records.

### Entity Relationship Summary

`DailyBar` records form the source time series. `DipEvent` records are detected from `DailyBar` transitions and forward windows. `AnalysisReport` summarizes all `DipEvent` outcomes for the run.

## 5. Development Phases

### Phase 1: Project Scaffolding

- **Goal:** Establish a runnable Python CLI project with dependency and config baseline.
- **Depends on:** None
- **Parallel streams:** No
- **Validation gate:** `python3 -m unittest discover -s tests` runs and exits successfully with at least one test.
- **Scope:**
  - Create package/module structure
  - Add requirements and env example
  - Add README usage instructions

### Phase 2: Data Ingestion

- **Goal:** Pull historical bars from Alpaca and normalize into internal `DailyBar` models.
- **Depends on:** Phase 1
- **Parallel streams:** No
- **Validation gate:** CLI can fetch bars for one symbol/date range with valid credentials and returns non-empty set.
- **Scope:**
  - Alpaca REST client
  - Pagination handling
  - Date parsing and sorting
  - Error handling for missing credentials/API failures

### Phase 3: Dip/Rebound Analysis Engine

- **Goal:** Compute event-level outcomes and aggregate confidence metrics.
- **Depends on:** Phase 2
- **Parallel streams:** No
- **Validation gate:** Unit tests verify event detection and Wilson confidence interval on deterministic fixtures.
- **Scope:**
  - Dip detection logic
  - Rebound success evaluation
  - Statistical summary + confidence interval

### Phase 4: CLI Reporting

- **Goal:** Provide configurable command-line inputs and readable output.
- **Depends on:** Phase 3
- **Parallel streams:** No
- **Validation gate:** Running CLI prints symbol summary and recent event outcomes without traceback.
- **Scope:**
  - argparse options
  - parameter validation
  - text report formatting
  - optional CSV input path

### Phase 5: Reliability and Guardrails

- **Goal:** Reduce misuse risk and clarify interpretation of probabilities.
- **Depends on:** Phase 4
- **Parallel streams:** No
- **Validation gate:** README documents assumptions/limits and CLI warns on tiny sample sizes.
- **Scope:**
  - small-sample warning
  - explicit risk notes
  - edge-case handling (insufficient bars, no dips)

## 6. Risks & Open Questions

- Small samples can produce misleading confidence intervals.
- Daily bars may miss intraday dynamics that affect real fill quality.
- The dip definition (close-to-close) may need alternatives for stronger signal quality.
