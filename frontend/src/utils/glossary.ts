// Plain-language definitions for the jargon the workbench uses. The `short`
// string is what the inline <Term> tooltip shows; `detail` is the longer
// explanation rendered on the Glossary page. Keys are stable ids so components
// can reference a term without duplicating the wording.

export type GlossaryGroup =
  | 'Signals & setup'
  | 'Results & metrics'
  | 'Model & validation'
  | 'Data & caching'

export interface GlossaryEntry {
  term: string
  short: string
  detail: string
  group: GlossaryGroup
}

export const GLOSSARY = {
  timeframe: {
    term: 'TF / timeframe',
    short: 'The bar size. 5m = one candle every 5 minutes.',
    detail:
      'How much time each candle covers. 5m means one bar per 5 minutes, 1d means one bar per day. Smaller bars give more signals but a shorter usable history.',
    group: 'Signals & setup'
  },
  episode: {
    term: 'Dip episode',
    short: 'One ≥5% drop, tracked as a single event.',
    detail:
      'A drawdown of 5% or more starts an episode. A bounce that then makes a new low does not start a fresh episode — it counts as another attempt. The episode ends when price closes back above the pre-dip high, or after a maximum duration.',
    group: 'Signals & setup'
  },
  attempt: {
    term: 'Attempt',
    short: 'Which bounce off the low this is: 1st try, 2nd try, …',
    detail:
      'The first time price tries to bounce off the episode low is attempt 1. If it fails and makes a lower low, the next bounce is attempt 2, and so on. Later attempts are often more reliable than the first.',
    group: 'Signals & setup'
  },
  fake_rebound: {
    term: 'Fake rebound',
    short: 'Bounced 1–2%, then made a new low.',
    detail:
      'The trap this whole tool is built around: a small bounce that looks like the turn, then fails and sets a fresh low. The Fake-rebound study compares buying the raw first bounce against waiting for confirmation.',
    group: 'Signals & setup'
  },
  uptrend: {
    term: 'Uptrend filter',
    short: 'Price above rising averages — the backdrop the setup assumes.',
    detail:
      'A set of checks that the stock is generally rising: price near/above its 50-day average, 50-day above 200-day, positive 6-month return, and a controlled 1-year drawdown. Dips inside an uptrend behave differently from dips in a downtrend.',
    group: 'Signals & setup'
  },
  sma_ema: {
    term: 'SMA / EMA',
    short: 'Simple and exponential moving averages of price.',
    detail:
      'SMA50 and SMA200 are the average price over the last 50 and 200 bars. EMA9 is a faster average that reacts quicker to recent prices. "Price above a rising average" is a common shorthand for an uptrend.',
    group: 'Signals & setup'
  },
  vwap: {
    term: 'VWAP',
    short: 'Volume-weighted average price — where most trading happened.',
    detail:
      'The average price weighted by how much volume traded at each level, so it reflects what most buyers actually paid. Reclaiming VWAP is a common confirmation that control has shifted back to buyers.',
    group: 'Signals & setup'
  },
  rsi: {
    term: 'RSI',
    short: 'Momentum on a 0–100 scale; low is "oversold".',
    detail:
      'Relative Strength Index, usually over 14 bars. It runs 0–100; low readings mean the stock has fallen hard recently, high readings mean it has risen hard. "RSI reclaim" means it is turning back up.',
    group: 'Signals & setup'
  },
  atr: {
    term: 'ATR',
    short: 'Average size of a bar’s move — a volatility gauge.',
    detail:
      'Average True Range: how much a bar typically moves, in price terms. Bigger ATR means a choppier, more volatile stock, which widens sensible target and stop distances.',
    group: 'Signals & setup'
  },
  confirmation: {
    term: 'Confirmation rule',
    short: 'The "wait for this before acting" test.',
    detail:
      'Instead of buying the first green bar, each rule waits for specific evidence — a higher low, reclaiming the 9-EMA or VWAP, a volume surge, or an RSI turn. The baseline "buy every dip bar" is included so every confirmation has to beat it.',
    group: 'Signals & setup'
  },
  triple_barrier: {
    term: 'Target / stop / max hold',
    short: 'The trade’s +1% goal, −2% bail-out, and 2-day time limit.',
    detail:
      'Every simulated trade has three exits: a profit target (+1% by default), a stop-loss (−2%), and a maximum holding time (2 trading days). Whichever is reached first decides the outcome, with costs and slippage included.',
    group: 'Signals & setup'
  },
  hit_rate: {
    term: 'Hit rate',
    short: '% of trades that reached the target before the stop.',
    detail:
      'Out of all trades taken, the share that hit +1% before −2%. With a +1% target and −2% stop you need a high hit rate just to break even, so this is best read together with Net EV.',
    group: 'Results & metrics'
  },
  net_ev: {
    term: 'Net EV / trade',
    short: 'Average profit per trade after costs.',
    detail:
      'The expected value of one trade once slippage and commission are subtracted. This — not hit rate alone — decides whether a rule is actually worth trading.',
    group: 'Results & metrics'
  },
  weekly_return: {
    term: 'Weekly return',
    short: 'The sequential return over the window, annualised to a week.',
    detail:
      'Compounds the sequential (one-position-at-a-time) trades across the data window and scales the result to a per-week figure. It is a sample estimate of the past, not a forecast.',
    group: 'Results & metrics'
  },
  trades_per_week: {
    term: 'Trades / week',
    short: 'How often the rule actually traded in the window.',
    detail:
      'A frequency measure. A high hit rate on two trades is far less meaningful than a moderate one on fifty, so always check how often the rule fired.',
    group: 'Results & metrics'
  },
  stop_rate: {
    term: 'Stop rate',
    short: 'Share of trades that hit the −2% stop.',
    detail:
      'How often the trade failed and exited at the stop. Together with the hit rate and timeout rate it adds up to 100% of outcomes.',
    group: 'Results & metrics'
  },
  fast_hit_rate: {
    term: 'Fast hit rate',
    short: 'Share that hit the target within the fast horizon (default 2h).',
    detail:
      'The fraction of trades that reached +1% within a short window — by default the first 2 hours. It answers "how quickly does this setup typically work, when it works?".',
    group: 'Results & metrics'
  },
  hold: {
    term: 'Median hold',
    short: 'Typical market minutes in the trade, excluding overnight gaps.',
    detail:
      'The middle amount of time a trade stayed open, counted in market hours only. This is the "minimal time in market" measure: shorter is generally better for a consistency-first strategy.',
    group: 'Results & metrics'
  },
  max_drawdown: {
    term: 'Max drawdown',
    short: 'The worst peak-to-trough dip in the equity curve.',
    detail:
      'The largest losing streak the strategy suffered over the window. A rule with a healthy return but a deep drawdown is harder to stick with in real life.',
    group: 'Results & metrics'
  },
  wilson_ci: {
    term: '95% CI',
    short: 'A range of uncertainty around the hit rate.',
    detail:
      'A Wilson confidence interval. Rather than a single hit-rate number, it shows the plausible range given how many trades there were — more trades give a tighter range. If the whole interval sits above 50%, the edge is more convincing.',
    group: 'Results & metrics'
  },
  exposure: {
    term: 'Exposure',
    short: 'Share of the time the strategy was in a trade.',
    detail:
      'The percentage of the window spent holding a position. Low exposure with a similar return means the strategy is more capital-efficient.',
    group: 'Results & metrics'
  },
  mfe_mae: {
    term: 'MFE / MAE',
    short: 'Best / worst an open trade ever got.',
    detail:
      'Maximum Favourable Excursion and Maximum Adverse Excursion: the largest profit and the largest loss the trade reached while it was open, regardless of where it exited. Useful for judging whether stops are too tight.',
    group: 'Results & metrics'
  },
  trend_score: {
    term: 'Trend score',
    short: 'How strongly the stock meets the uptrend checks (0–1).',
    detail:
      'A 0–1 score summarising how many uptrend conditions the stock satisfies. Higher means a cleaner, stronger uptrend backdrop for dips.',
    group: 'Results & metrics'
  },
  range_days: {
    term: '5% days',
    short: 'Days in the last 60 with an intraday range of 5%+.',
    detail:
      'A count of recent days that swung at least 5% from high to low. It is a quick volatility screen: too few and a 5% dip is rare; too many and the moves may be chaotic.',
    group: 'Results & metrics'
  },
  dips_per_month: {
    term: 'Dips / mo',
    short: 'Average number of ≥5% dip events per month.',
    detail:
      'How frequently the stock actually produces the dip setup this tool studies. A stock with almost no dips is a poor candidate no matter how good its trend is.',
    group: 'Results & metrics'
  },
  readiness: {
    term: 'Automation readiness',
    short: 'A plain-language verdict on whether the setup has an edge.',
    detail:
      'A 0–100 score and one of: promising, fragile, needs more data, no demonstrated edge, or not qualified. It requires a genuine uptrend, enough sequential trades, a positive walk-forward estimate, and a hit-rate interval above 50%. It is still a historical estimate, not a guarantee.',
    group: 'Results & metrics'
  },
  qualification: {
    term: 'Status',
    short: 'qualified / watch / reject — a first-pass screen.',
    detail:
      'A coarse qualification of the stock: qualified means it passes the trend, volatility and dip checks; watch means borderline; reject means it fails. It is a gate, not a recommendation.',
    group: 'Results & metrics'
  },
  recommended_rule: {
    term: 'Best rule',
    short: 'The confirmation rule that scored highest in testing.',
    detail:
      'The rule selected by the ranking (shrunk weekly return minus drawdown). The Analyzer shows how it performed out-of-sample, which is the number to trust most.',
    group: 'Results & metrics'
  },
  oos: {
    term: 'OOS / walk-forward',
    short: 'Tested on data the rule had not seen — the honest number.',
    detail:
      'Out-of-sample results. A rule is chosen on one stretch of history and then measured on the next, unseen stretch. This guards against cherry-picking and is the most trustworthy figure on the page.',
    group: 'Model & validation'
  },
  auc: {
    term: 'AUC',
    short: 'Model ranking skill. 0.5 = a coin flip.',
    detail:
      'Area Under the ROC Curve: how well the model ranks winning setups above losing ones. 0.5 is random, 0.6–0.7 is modest, higher is stronger. Near 0.5 means the model adds little.',
    group: 'Model & validation'
  },
  brier: {
    term: 'Brier',
    short: 'Calibration: how close predicted probabilities are to reality.',
    detail:
      'Brier score measures how accurate the model’s probabilities are. Closer to the base rate means the model is not really calibrated — its confidence numbers should not be taken at face value.',
    group: 'Model & validation'
  },
  base_rate: {
    term: 'Base rate',
    short: 'The overall share of winning setups, with no model.',
    detail:
      'The unconditional hit rate across all setups. A model is only useful if it beats this baseline; it is the yardstick the model’s filtered results are compared against.',
    group: 'Model & validation'
  },
  threshold: {
    term: 'Threshold',
    short: 'The model probability below which a trade is skipped.',
    detail:
      'The cutoff applied to the model’s probability before opening a trade. It is chosen on early out-of-sample data and then evaluated on the held-out remainder, so it is not tuned on the numbers you are reading.',
    group: 'Model & validation'
  },
  walk_forward: {
    term: 'Walk-forward folds',
    short: 'Repeated train-then-test splits across the history.',
    detail:
      'The history is cut into successive windows: pick the rule on one, measure on the next, roll forward, repeat. Consistent results across folds are more convincing than one good overall number.',
    group: 'Model & validation'
  }
} satisfies Record<string, GlossaryEntry>

export type GlossaryKey = keyof typeof GLOSSARY

export const GLOSSARY_GROUPS: GlossaryGroup[] = [
  'Signals & setup',
  'Results & metrics',
  'Model & validation',
  'Data & caching'
]

export function glossaryByGroup(): Array<{
  group: GlossaryGroup
  entries: Array<{ key: GlossaryKey; entry: GlossaryEntry }>
}> {
  return GLOSSARY_GROUPS.map((group) => ({
    group,
    entries: (Object.keys(GLOSSARY) as GlossaryKey[])
      .filter((key) => GLOSSARY[key].group === group)
      .map((key) => ({ key, entry: GLOSSARY[key] }))
  })).filter((section) => section.entries.length > 0)
}
