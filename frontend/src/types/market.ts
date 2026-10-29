export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '1d'

export interface AnalysisConfig {
  timeframe: Timeframe
  dip_threshold_pct: number
  dip_lookback_days: number
  target_pct: number
  stop_pct: number
  stop_mode: 'fixed' | 'episode_low'
  stop_buffer_pct: number
  min_stop_pct: number
  max_stop_pct: number
  max_hold_days: number
  fast_horizon_minutes: number
  max_runup_from_low_pct: number
  attempt_min_pct: number
  episode_max_days: number
  swing_pivot_bars: number
  entry_slippage_bps: number
  exit_slippage_bps: number
  commission_bps: number
  exclude_first_minutes: number
  exclude_last_minutes: number
  only_uptrend_signals: boolean
  uptrend_min_score: number
  min_daily_bars: number
  min_intraday_bars: number
  min_price: number
  min_dollar_volume: number
  volatility_lookback_days: number
  volatility_min_range_days: number
  volatility_min_atr_pct: number
  max_distance_from_sma50_pct: number
  max_below_sma50_pct: number
  max_drawdown_1y_pct: number
  uptrend_min_6m_return_pct: number
  uptrend_require_sma200: boolean
  uptrend_require_sma50_gt_sma200: boolean
  daily_recovery_target_pct: number
  daily_recovery_window_days: number
  min_samples_for_model: number
  model_threshold: number
  walk_forward_folds: number
  min_trades_for_rule: number
  min_trades_for_threshold: number
  enabled_rules: string[] | null
  daily_history_days: number
  intraday_history_days: number
}

export interface ConfigField {
  key: keyof AnalysisConfig
  label: string
  type: 'number' | 'boolean' | 'select'
  min?: number
  max?: number
  step?: number
  options?: string[]
}

export interface ConfigSection {
  id: string
  label: string
  fields: ConfigField[]
}

export interface MarketConfigResponse {
  defaults: AnalysisConfig
  schema: { sections: ConfigSection[] }
  timeframes: Timeframe[]
  provider: Record<string, unknown>
  provider_warnings: string[]
  settings: {
    default_notional: number
    paper_enabled: boolean
    screen_default_limit: number
  }
  universe_size: number
  disclaimer: string
}

export interface QualificationReason {
  code: string
  label: string
  passed: boolean
  value: string
  target: string
  detail?: string
}

export interface BucketStat {
  bucket: string
  signals: number
  hit_rate: number
  ci_low: number
  ci_high: number
  net_ev_pct: number
}

export interface RuleStats {
  rule_id: string
  name?: string
  description?: string
  family?: string
  confirmations?: string[]
  signals: number
  signal_hit_rate: number
  signal_net_ev_pct: number
  trades: number
  successes: number
  hit_rate: number
  hit_rate_low: number
  hit_rate_high: number
  net_ev_pct: number
  gross_ev_pct: number
  stop_rate: number
  timeout_rate: number
  fast_hit_rate: number
  median_holding_minutes: number
  mean_holding_minutes: number
  trades_per_week: number
  weekly_return_pct: number
  total_return_pct: number
  max_drawdown_pct: number
  avg_mfe_pct: number
  avg_mae_pct: number
  profit_factor: number | null
  exposure_pct: number
  rank_score?: number
  by_attempt: BucketStat[]
  by_depth: BucketStat[]
  by_time_of_day: BucketStat[]
  by_runup: BucketStat[]
  by_failed_bounce: BucketStat[]
}

export interface ModelFeature {
  name: string
  coefficient: number
  odds_ratio: number
  importance: number
}

export interface CalibrationBin {
  bin: number
  low: number
  high: number
  count: number
  predicted: number
  actual: number
}

export interface ThresholdRow {
  threshold: number
  trades: number
  hit_rate: number
  net_ev_pct: number
  trades_per_week: number
  weekly_return_pct: number
  max_drawdown_pct: number
}

export interface WalkForwardFold {
  fold: number
  test_start: string
  test_end?: string
  selected_rule?: string | null
  train_trades?: number
  train_weekly_return_pct?: number
  test_trades?: number
  test_trades_per_week?: number
  test_hit_rate?: number
  test_net_ev_pct?: number
  test_weekly_return_pct?: number
  test_stop_rate?: number
  train_samples?: number
  test_samples?: number
  auc?: number | null
  brier?: number | null
  base_rate?: number | null
  accuracy?: number | null
  reason?: string
}

export interface ModelInfo {
  available: boolean
  reason: string
  model_type?: string
  samples?: number
  train_samples?: number
  test_samples?: number
  features: ModelFeature[]
  auc?: number | null
  brier?: number | null
  log_loss?: number | null
  accuracy?: number | null
  base_rate?: number | null
  calibration: CalibrationBin[]
  walk_forward: WalkForwardFold[]
  threshold_curve: ThresholdRow[]
  recommended_threshold: number
  filtered_stats: RuleStats | Record<string, never>
  unfiltered_oos_stats?: RuleStats | Record<string, never>
  use_filter?: boolean
  filter_eval?: {
    method?: string
    selection_samples?: number
    eval_samples?: number
    selection_threshold?: number
  }
  spec?: Record<string, unknown> | null
  fast?: {
    samples?: number
    positives?: number
    negatives?: number
    auc?: number | null
    brier?: number | null
    base_rate?: number | null
    calibration?: CalibrationBin[]
    walk_forward?: WalkForwardFold[]
    spec?: Record<string, unknown> | null
  } | null
}

export interface Trade {
  rule_id: string
  signal_index: number
  signal_ts: string
  entry_ts: string
  exit_ts: string
  entry_price: number
  exit_price: number
  return_pct: number
  net_return_pct: number
  exit_reason: 'target' | 'stop' | 'timeout' | 'end_of_data'
  success: boolean
  fast_success: boolean
  holding_bars: number
  holding_minutes: number
  holding_trading_minutes: number
  mfe_pct: number
  mae_pct: number
  target_price: number
  stop_price: number
  probability: number | null
  probability_fast: number | null
  features: {
    episode_depth_pct: number
    drawdown_from_high_pct: number
    drawdown_from_prior_close_pct: number
    runup_from_low_pct: number
    bars_since_episode_low: number
    attempt_number: number
    failed_bounces: number
    failed_bounces_1pct: number
    volume_ratio20: number
    rsi14: number | null
    atr_pct: number
    price_vs_vwap_pct: number
    higher_low: boolean
    close_above_prior_swing_high: boolean
    minutes_since_open: number
    daily_trend_score: number
    gap_pct: number
  }
}

export interface LevelInfo {
  entry_estimate: number
  target: number
  stop: number
  target_pct: number
  stop_pct: number
}

export interface FiredRule {
  id: string
  name: string
  family: string
  baseline: boolean
}

export interface SignalRead {
  state: 'signal' | 'watching' | 'no_setup' | 'no_data'
  detail: string
  ts?: string
  price?: number
  candidate?: boolean
  episode_active?: boolean
  episode_depth_pct?: number
  episode_recovery_pct?: number
  runup_from_low_pct?: number
  bars_since_episode_low?: number
  attempt_number?: number
  failed_bounces?: number
  failed_bounces_1pct?: number
  higher_low?: boolean
  close_above_prior_high?: boolean
  close_above_ema9?: boolean
  close_above_vwap?: boolean
  rsi14?: number | null
  volume_ratio20?: number
  daily_trend_score?: number
  fired_rules: FiredRule[]
  recommended_fire?: boolean
  probability: number | null
  probability_fast: number | null
  levels: LevelInfo
  waiting_for: string[]
  fake_rebound_risk: { level: string; detail: string }
  recommended_rule_id?: string | null
}

export interface Episode {
  id: number
  start: string
  end: string | null
  reference_high: number
  low: number
  low_ts: string
  depth_pct: number
  failed_bounces: number
  failed_bounces_1pct: number
  recovered: boolean
  duration_bars: number
  max_bounce_pct: number
}

export interface EpisodeSummary {
  count: number
  per_month: number
  fake_rebound_rate: number
  multi_leg_rate: number
  recovered_rate: number
  avg_depth_pct: number
  median_duration_bars: number
  avg_max_bounce_pct: number
  avg_failed_bounces: number
  interpretation: string
}

export interface DailyProfile {
  bars: number
  start: string | null
  end: string | null
  price: number
  qualification: {
    status: 'qualified' | 'watch' | 'reject'
    score: number
    reasons: QualificationReason[]
    trend_ok?: boolean
    volatility_ok?: boolean
    dip_ok?: boolean
  }
  uptrend: Record<string, number | boolean | null>
  volatility: Record<string, number>
  dips: {
    count: number
    per_month: number
    avg_dip_pct: number
    fake_rebound_count: number
    fake_rebound_rate: number
    recover_1pct_count: number
    recover_1pct_rate: number
    recover_target_count: number
    recover_target_rate: number
    median_days_to_1pct: number | null
    median_days_to_target: number | null
    avg_max_rebound_pct: number
    avg_max_drawdown_pct: number
    events: Array<Record<string, unknown>>
  }
  warnings: string[]
}

export interface RecommendedInfo {
  rule_id: string
  name: string
  description: string
  family: string
  confirmations: string[]
  stats: RuleStats
  walk_forward_oos: RuleStats | null
  selection_reason: string
  use_model_filter: boolean
  threshold: number | null
  filtered_stats: RuleStats | Record<string, never>
  attempt_analysis: {
    rule_id: string
    by_attempt: BucketStat[]
    by_failed_bounce: BucketStat[]
    interpretation?: string
  } | null
}

export interface FakeReboundStudy {
  baseline_first_attempt: BucketStat
  baseline_after_failed_bounce: BucketStat | null
  confirmed_first_attempt: BucketStat
  confirmed_after_failed_bounce: BucketStat | null
  confirmed_label?: string
  interpretation: string
}

export interface ReadinessBullet {
  label: string
  value: string
  tone: 'good' | 'bad' | 'warn' | 'neutral'
}

export interface AutomationReadiness {
  status: 'promising' | 'fragile' | 'needs_more_data' | 'no_edge' | 'not_qualified'
  score: number
  summary: string
  bullets: ReadinessBullet[]
  metrics: {
    oos_trades: number
    oos_hit_rate: number
    oos_hit_rate_low: number
    oos_hit_rate_high: number
    oos_net_ev_pct: number
    oos_weekly_return_pct: number
    oos_max_drawdown_pct: number
    median_holding_minutes: number
    trades_per_week: number
    fake_rebound_lift: number
    model_auc: number | null
    model_brier: number | null
    max_rule_trades: number
  }
}

export interface Profile {
  meta: {
    symbol: string
    generated_at: string
    engine_version: string
    config_hash: string
    effective_config_hash: string
    mode: Timeframe
    timeframe: Timeframe
    fast_horizon_label: string
    bars_analyzed: number
    candidate_bars: number
    episodes: number
    disclaimer: string
    error?: string
  }
  config: AnalysisConfig
  requested_config: AnalysisConfig
  data: {
    mode: Timeframe
    timeframe: Timeframe
    requested_timeframe: Timeframe
    fallback: boolean
    daily: { bars: number; start: string | null; end: string | null; source: string | null }
    intraday: { bars: number; start: string | null; end: string | null; source: string | null; used: boolean }
    quality: Record<string, number>
    coverage: Record<string, unknown>
  }
  qualification: DailyProfile['qualification']
  daily: DailyProfile
  episodes: Episode[]
  episode_summary: EpisodeSummary
  automation_readiness: AutomationReadiness
  rules: RuleStats[]
  recommended: RecommendedInfo | null
  model: ModelInfo
  walk_forward: {
    available: boolean
    reason: string
    folds: WalkForwardFold[]
    selected_counts?: Record<string, number>
    oos?: RuleStats | null
  }
  attempt_analysis: RecommendedInfo['attempt_analysis']
  fake_rebound_study: FakeReboundStudy | null
  signal_read: SignalRead
  trades: Trade[]
  equity_curve: Array<{ ts: string; equity: number; return_pct: number; rule_id: string }>
  warnings: string[]
  cache?: { cached: boolean; data_version: number; built_at: string }
}

export interface ChartBar {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface SearchResult {
  symbol: string
  name: string
  sector: string
  in_database: boolean
}

export interface WatchlistItem {
  id: number
  security: { symbol: string; name: string; exchange: string; active: boolean; data_version: number }
  active: boolean
  note: string
  config_hash: string
  last_checked_at: string | null
  last_price: number | null
  last_signal: SignalRead | Record<string, never>
  open_trade: PaperTrade | null
  added_at: string
}

export interface PaperTrade {
  id: number
  symbol: string
  status: 'open' | 'closed'
  rule_id: string
  config_hash: string
  entry_ts: string
  entry_price: number
  notional: number
  qty: number
  target_price: number
  stop_price: number
  probability: number | null
  signal: SignalRead | Record<string, never>
  exit_ts: string | null
  exit_price: number | null
  exit_reason: string
  return_pct: number | null
  pnl: number | null
  created_at: string
  updated_at: string
}

export interface PaperStats {
  closed_trades: number
  open_trades: number
  wins: number
  win_rate: number
  avg_return_pct: number
  total_return_pct: number
  total_pnl: number
  by_rule: Record<string, {
    trades: number
    wins: number
    return_sum: number
    pnl: number
    win_rate: number
    avg_return_pct: number
  }>
}

export interface ScreenResult {
  symbol: string
  status: 'qualified' | 'watch' | 'reject'
  score: number
  price?: number
  uptrend?: Record<string, number | boolean | null>
  volatility?: Record<string, number>
  dips?: Record<string, number | null>
  qualification?: DailyProfile['qualification']
  recommended?: RuleStats | null
  episode_summary?: EpisodeSummary
  readiness?: AutomationReadiness | null
  model?: { available: boolean; auc: number | null; threshold: number | null }
  warnings: string[]
  error: string
  profile_error?: string
}

export interface ScreenRun {
  id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  config: AnalysisConfig
  symbols: string[]
  total: number
  completed: number
  progress_pct: number
  with_intraday: boolean
  source: string
  results: ScreenResult[]
  error: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface LiveCheckResponse {
  symbol: string
  signal_read: SignalRead
  profile_summary: RuleStats | Record<string, never>
  config: AnalysisConfig
  warnings: string[]
  data_version: number
}

export interface CoverageResponse {
  symbol: string
  data_version: number
  coverage: Record<string, {
    timeframe: string
    earliest_ts: string | null
    latest_ts: string | null
    unavailable_before: string | null
    bar_count: number
    provider: string
    last_attempt_at: string | null
    last_success_at: string | null
    last_error: string
  }>
}
