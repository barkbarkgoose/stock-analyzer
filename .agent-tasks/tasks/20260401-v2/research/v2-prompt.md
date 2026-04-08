I want to evolve this project from a simple daily dip/rebound analyzer into a modular backtesting and research tool for identifying stocks that show repeatable dip-then-rebound behavior.

The end goal is NOT just a single backtest script. I want a system that can:

1. rapidly scan many stocks and rank them by whether they fit a desired “repeated dip and rebound” profile
2. identify which days are worth deeper intraday analysis instead of blindly analyzing every minute of every day
3. run a more realistic intraday backtest using a state machine
4. test multiple anchor definitions, thresholds, and cooldown rules
5. help determine which parameter combinations are best for different time horizons:
   - consistent monthly income
   - quarterly performance
   - yearly performance / compounding
6. remain simple enough to run from the console for now, with clean Python architecture and no unnecessary UI

Tech / stack requirements:
- Python
- use Alpaca API for market data if needed, but design the code so data source can be swapped later
- no framework unless clearly needed
- console output is fine
- code should be modular, readable, and built for iteration
- prioritize architecture and analysis workflow over polish

NOTE: if not done yet, we want to make sure that we avoid repeat calls to an api for getting the history of a stock.  ideally we want to create a profile for it locally either in a database or in a file that is easy to parse.  A database is good because we can look up dates or time periods if we're considering getting finer granularity within that timeframe, in which case we'd go get additional candles/entries from the api and augment whatever we already have.

IMPORTANT - EXISTING CODE ISSUE: The current `analysis.py` (stock_rebound_analyzer/analysis.py) has lookahead bias in the dip detection logic. On line 47 it uses `lookahead = bars[idx + 1 : idx + 1 + rebound_window_days]` to look into future bars when determining if a dip "succeeded." This must be fixed before building new components on top of it. The new backtester must NOT repeat this mistake — at any point in time, only information available up to that bar should be used for decisions.

Core concept:
I want to study stocks that frequently experience sharp drops and then predictable rebounds. The current daily-level version was only a first pass. The next phase needs to distinguish:
- which stocks are worth studying
- which days are worth zooming into
- which intraday patterns actually provide tradable signals

I do NOT want to naively analyze every 5-minute or 1-minute bar of every day for every stock. I want a pipeline that narrows the problem:

PHASE A: broad stock screening
PHASE B: identify qualifying days / day types
PHASE C: intraday strategy simulation on those narrowed candidates
PHASE D: parameter comparison and reporting

Create tasks grouped by these phases, in this order. Complete each phase before moving to the next.

--------------------------------
SYSTEM DESIGN GOALS
--------------------------------

Build this as a research framework with clearly separated pieces:

1. Universe Scanner
A component that can analyze many stocks over a historical period and score them based on whether they fit a desired profile such as:
- frequency of large drops
- frequency of rebounds after those drops
- consistency of rebound size
- average and worst drawdown after dip
- volatility profile
- how often setups occur per week/month
- whether the stock has enough liquidity / tradability to be realistic

The scanner should output ranked candidates and explain WHY each stock ranked well.

2. Day Selector / Day Classifier
A component that identifies which days deserve intraday analysis instead of analyzing all days equally.

It should be able to:
- detect qualifying dip days
- classify day types if possible
- compare normal days vs high-volatility days
- identify “watch-triggered” days where the stock crossed a relevant drop threshold
- optionally group days into categories such as:
  - immediate rebound days
  - continued selloff days
  - choppy reversal days
  - gap-down recovery days
  - trend-down failure days

This does not need to use machine learning unless it is genuinely useful. Rule-based categorization is fine to start.

3. Intraday Backtester
A realistic state-machine backtester with explicit states:
- idle
- armed
- in_trade
- cooldown

This is critical.

The logic should work like this in general:
- stock starts in idle
- when a configured drop threshold is hit relative to an anchor, the stock becomes armed
- while armed, we assume it may continue falling, so we do NOT buy immediately
- while armed, track the local low after trigger
- entry only happens if a rebound confirmation occurs according to configuration
- once in trade, manage target / stop / time-based exit
- after exit, move to cooldown and ignore new entries until cooldown ends
- after cooldown, return to idle

This state machine should be implemented clearly and explicitly, not as loose nested conditionals.

4. Parameter Sweep / Grid Search
The system must support testing combinations of:
- trigger drop thresholds
- rebound confirmation thresholds
- profit targets
- stop losses
- cooldown periods
- anchor definitions
- time stop / max holding period
- bar granularity

It should be easy to add new parameters later.

5. Reporting / Evaluation
The system must report more than just win rate.

It should calculate:
- total trades
- trades per week/month
- win rate
- average win
- average loss
- expectancy / expected value per trade
- total return
- max drawdown
- profit factor
- average hold time
- time in market
- capital usage / opportunity cost if relevant
- monthly performance distribution
- quarterly performance distribution
- yearly performance distribution

I want results that help evaluate:
- “best for frequent small income”
- “best for smoother longer-term compounding”
- “best risk-adjusted profile”

--------------------------------
BASELINE / ANCHOR EXPERIMENTS
--------------------------------

A major requirement is that the system must support trying multiple anchor definitions.

Examples:
- previous day close
- current day open
- rolling intraday high since market open
- VWAP-related anchor if appropriate
- prior N-bar high
- session high after open

I want the architecture to make anchors pluggable. I do not want one hardcoded anchor.

For each anchor, the system should allow:
- triggering a watch when price falls by X% relative to that anchor
- tracking what happens after trigger
- comparing whether some anchors produce cleaner entries than others

--------------------------------
INTRADAY GRANULARITY REQUIREMENTS
--------------------------------

I want adjustable granularity depending on activity.

Examples:
- broad screening may use daily bars
- qualifying days may use 15-minute or 5-minute bars
- “hot zones” or “go time” periods may use 1-minute bars
- system should allow analyzing only the important section of a day once a watch is triggered

In other words:
- do not brute force everything at max resolution all the time
- allow zooming in where action matters

A good architecture would allow:
- daily scan first
- then fetch / analyze higher-resolution data only for selected stocks and days
- optionally zoom into the portion of the day after a watch trigger occurs

Please design the code to support this progressive narrowing.

--------------------------------
STRATEGY RESEARCH REQUIREMENTS
--------------------------------

I want to test ideas like:

1. A target drop triggers a watch, not a buy
2. The stock may continue falling, so we wait
3. Buy only after rebound confirmation from the local low
4. Exit at a modest gain, not by trying to capture the entire rebound
5. If the rebound was false, cut the loss early
6. Use cooldown to avoid repeated chop / re-entry noise
7. Compare whether bigger drop triggers produce better entries
8. Compare whether waiting for confirmation helps or hurts
9. Compare same-day strategies vs multi-day hold windows

I especially want the system to help answer questions like:
- Is waiting for rebound confirmation actually better than buying immediately?
- What trigger drop sizes produce the best setups?
- How much confirmation is too much and causes late entries?
- What cooldown avoids overtrading while preserving opportunity?
- Do some stocks behave better with same-day exit vs multi-day hold?
- Are there recurring intraday patterns or “types of days” that are significantly more favorable?

--------------------------------
IMPORTANT ALGORITHMIC REQUIREMENTS
--------------------------------

These are critical and should be implemented carefully:

1. State machine
Use explicit state transitions:
- idle -> armed -> in_trade -> cooldown -> idle

2. Trigger/watch logic
A drop threshold should trigger a WATCH state, not an immediate buy.

3. Local low tracking
After a watch is triggered, track the lowest price seen before rebound confirmation.

4. Rebound confirmation
Entry occurs only when price rises by configured percentage from the post-trigger local low.

5. Exit logic
Support:
- profit target
- stop loss
- time stop
- optional end-of-day exit

6. Cooldown
Cooldown should be configurable by:
- number of bars
- minutes
- rest of session
- next session
Make it flexible.

7. No accidental lookahead bias
Be careful not to use future bars when determining entries/exits/day classification.

8. Clean experiment structure
Results should be reproducible and comparable across parameter sets.

--------------------------------
WHAT I WANT BUILT
--------------------------------

Please build the next phase of this project with:

1. a proposed folder structure
2. clean modules/classes for:
   - data access
   - stock screening
   - day selection / classification
   - anchors
   - strategy rules
   - state-machine backtester
   - parameter sweep
   - metrics/reporting
3. a minimal CLI or console entry point
4. a config-driven approach so strategy parameters can be adjusted without rewriting core logic
5. sample output that shows how results would look
6. docstrings / comments explaining the architecture
7. a short explanation of assumptions and where the model could be misleading

--------------------------------
ARCHITECTURAL PREFERENCES
--------------------------------

Prefer a design similar to:

- /data
- /screeners
- /selectors
- /anchors
- /strategies
- /backtests
- /metrics
- /reports
- /config
- /main.py or /cli.py

Use dataclasses / typed models where helpful.
Favor composable pieces over a giant script.
Keep logic testable.
Avoid overengineering, but do not collapse everything into one file.

--------------------------------
DELIVERABLE STYLE
--------------------------------

I do NOT want you to obsess over framework or syntax choices first.
I want you to focus on the end goal and architecture.

Your response should include:
1. a concise architecture plan
2. the folder structure
3. the core data models / classes
4. the backtesting flow
5. how screening narrows into intraday analysis
6. where the parameter grid fits in
7. Python code scaffolding for the next phase
8. enough implementation to make the structure real, even if some parts are stubbed

If you need to leave some advanced analysis as placeholders, that is fine, but the core flow should be real and coherent.

Most important: build this so I can iteratively improve it into a genuine research and backtesting tool rather than another disposable script.
