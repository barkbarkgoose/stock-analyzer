"""Causal feature engineering and dip-episode state tracking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .bars import normalize_bars
from .config import AnalysisConfig
from .indicators import (
    atr,
    bars_per_session,
    confirmed_swings,
    ema,
    rolling_extreme,
    rolling_mean,
    rolling_std,
    rsi,
    session_date,
    session_minutes,
    session_progress,
)
from .types import Bar, DailyContext, EpisodeRecord, FeatureRow


@dataclass(slots=True)
class FeatureSeries:
    symbol: str
    timeframe: str
    rows: list[FeatureRow]
    episodes: list[EpisodeRecord]
    bars_per_day: float


@dataclass(slots=True)
class _EpisodeState:
    active: bool = False
    episode_id: int = 0
    start_index: int | None = None
    start_ts: object | None = None
    reference_high: float = 0.0
    low: float = 0.0
    low_index: int = 0
    low_ts: object | None = None
    max_high_since_low: float = 0.0
    max_high_since_low_index: int = 0
    failed_bounces: int = 0
    failed_bounces_1pct: int = 0
    last_new_low_index: int = 0
    max_bounce_pct: float = 0.0

    @property
    def attempt_number(self) -> int:
        return self.failed_bounces + 1


class _EpisodeTracker:
    """Tracks a multi-leg dip as one episode.

    A key modelling decision: a 5% drop, a 1-2% bounce and then a further 8%
    drop must stay in the *same* episode.  If we reset the episode on every new
    low, the second leg would look like a fresh first attempt and the model
    could never learn that the initial bounce was a fake one.  The tracker
    therefore only ends an episode on a close above the pre-dip reference high
    or after a maximum duration.
    """

    def __init__(self, config: AnalysisConfig) -> None:
        self.config = config
        self.state = _EpisodeState()
        self.episodes: list[EpisodeRecord] = []

    def update(
        self,
        index: int,
        bar: Bar,
        prior_high: float | None,
        prior_close: float | None,
    ) -> _EpisodeState:
        state = self.state
        cfg = self.config

        if not state.active:
            reference = prior_high or bar.high
            if prior_close and prior_close > reference:
                reference = prior_close
            depth_low = (reference - bar.low) / reference * 100.0
            depth_close = (reference - bar.close) / reference * 100.0
            prior_close_depth = (
                (prior_close - bar.close) / prior_close * 100.0
                if prior_close
                else 0.0
            )
            if max(depth_low, depth_close, prior_close_depth) >= cfg.dip_threshold_pct:
                state.active = True
                state.episode_id += 1
                state.start_index = index
                state.start_ts = bar.ts
                state.reference_high = reference
                state.low = bar.low
                state.low_index = index
                state.low_ts = bar.ts
                state.max_high_since_low = bar.high
                state.max_high_since_low_index = index
                state.failed_bounces = 0
                state.failed_bounces_1pct = 0
                state.last_new_low_index = index
                state.max_bounce_pct = 0.0
            return state

        # Update the best bounce from the current low before considering a new
        # low.  This is what distinguishes a fake bounce from a genuine reclaim.
        if bar.high > state.max_high_since_low:
            state.max_high_since_low = bar.high
            state.max_high_since_low_index = index
        if state.low > 0:
            state.max_bounce_pct = max(
                state.max_bounce_pct,
                (state.max_high_since_low / state.low - 1.0) * 100.0,
            )

        if bar.low < state.low:
            bounce_pct = (state.max_high_since_low / state.low - 1.0) * 100.0
            if bounce_pct >= cfg.attempt_min_pct:
                state.failed_bounces += 1
            if bounce_pct >= 1.0:
                state.failed_bounces_1pct += 1
            state.low = bar.low
            state.low_index = index
            state.low_ts = bar.ts
            state.last_new_low_index = index
            state.max_high_since_low = bar.high
            state.max_high_since_low_index = index

        recovered = bar.close >= state.reference_high
        expired = (
            state.start_index is not None
            and index - state.start_index >= cfg.episode_max_bars
        )
        if recovered or expired:
            self.episodes.append(
                EpisodeRecord(
                    episode_id=state.episode_id,
                    start_ts=state.start_ts,  # type: ignore[arg-type]
                    end_ts=bar.ts,
                    reference_high=state.reference_high,
                    low=state.low,
                    low_ts=state.low_ts,  # type: ignore[arg-type]
                    depth_pct=(state.reference_high - state.low)
                    / state.reference_high
                    * 100.0,
                    failed_bounces=state.failed_bounces,
                    failed_bounces_1pct=state.failed_bounces_1pct,
                    recovered=recovered,
                    duration_bars=index - (state.start_index or index),
                    max_bounce_pct=state.max_bounce_pct,
                )
            )
            state.active = False

        return state


def _default_context(as_of: date) -> DailyContext:
    return DailyContext(
        as_of=as_of,
        close=0.0,
        sma20=None,
        sma50=None,
        sma200=None,
        above_sma20=False,
        above_sma50=False,
        above_sma200=False,
        sma50_gt_sma200=False,
        return_6m_pct=0.0,
        return_1y_pct=0.0,
        distance_sma50_pct=0.0,
        atr14_pct=0.0,
        range_5pct_days_60d=0,
        close_5pct_days_60d=0,
        dip_count_60d=0,
        avg_dollar_volume_60d=0.0,
        max_drawdown_1y_pct=0.0,
        trend_score=0.0,
        last_return_pct=0.0,
        two_day_return_pct=0.0,
        last_range_pct=0.0,
    )


def _prior_highs(highs: list[float], lookback: int) -> list[float | None]:
    """Highest high in the prior ``lookback`` bars (current excluded)."""

    out: list[float | None] = [None] * len(highs)
    dq: list[int] = []
    head = 0
    for i in range(len(highs)):
        # dq contains indices in [i-lookback, i-1]
        while len(dq) > head and dq[head] < i - lookback:
            head += 1
        if len(dq) > head:
            out[i] = highs[dq[head]]
        while len(dq) > head and highs[dq[-1]] <= highs[i]:
            dq.pop()
        dq.append(i)
        if head > 1024 and head * 2 > len(dq):
            dq = dq[head:]
            head = 0
    return out


def _expanding_or_rolling_min(
    lows: list[float], window: int
) -> tuple[list[float], list[int]]:
    out_values: list[float] = []
    out_indices: list[int] = []
    rolling_values, rolling_indices = rolling_extreme(lows, window, is_max=False)
    for i in range(len(lows)):
        if i < window - 1:
            window_lows = lows[: i + 1]
            best = min(range(len(window_lows)), key=window_lows.__getitem__)
            out_values.append(window_lows[best])
            out_indices.append(best)
        else:
            value = rolling_values[i]
            idx = rolling_indices[i]
            assert value is not None and idx is not None
            out_values.append(value)
            out_indices.append(idx)
    return out_values, out_indices


def build_features(
    bars: list[Bar],
    config: AnalysisConfig,
    *,
    daily_context: dict[date, DailyContext] | None = None,
    symbol: str | None = None,
) -> FeatureSeries:
    """Build one causal :class:`FeatureRow` per bar.

    ``daily_context`` is keyed by session date.  The caller is responsible for
    making it point-in-time correct: for intraday studies the context for
    session D must only use daily bars completed *before* D.  This is the most
    common source of subtle look-ahead bias in this kind of research, so it is
    deliberately explicit.
    """

    bars = normalize_bars(bars, timeframe=config.timeframe)
    n = len(bars)
    resolved_symbol = symbol or (bars[0].symbol if bars else "")
    if n == 0:
        return FeatureSeries(
            symbol=resolved_symbol,
            timeframe=config.timeframe,
            rows=[],
            episodes=[],
            bars_per_day=1.0,
        )

    timeframe = config.timeframe
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    volumes = [float(b.volume) for b in bars]
    dollar_volumes = [b.dollar_volume for b in bars]
    sessions = [session_date(b) for b in bars]
    bpd = bars_per_session(bars)

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    atr14 = atr(bars, 14)
    volatility_window = 20
    log_returns = [0.0]
    for i in range(1, n):
        prev = closes[i - 1]
        log_returns.append(math.log(closes[i] / prev) if prev > 0 else 0.0)
    realized_vol = rolling_std(log_returns, volatility_window)
    volume_mean = rolling_mean(volumes, 20)
    dollar_mean = rolling_mean(dollar_volumes, 20)

    lookback = config.dip_lookback_bars
    prior_highs = _prior_highs(highs, lookback)
    rolling_lows, rolling_low_idx = _expanding_or_rolling_min(lows, lookback)

    last_swing_low, prev_swing_low, last_swing_high, prev_swing_high = (
        confirmed_swings(bars, config.swing_pivot_bars)
    )

    # Session-level context (prior close, gap, VWAP, bar counter).
    session_last_close: dict[date, float] = {}
    for bar, sd in zip(bars, sessions):
        session_last_close[sd] = bar.close
    unique_sessions = sorted(session_last_close)
    previous_session = {
        sd: (unique_sessions[i - 1] if i > 0 else None)
        for i, sd in enumerate(unique_sessions)
    }
    session_first_open: dict[date, float] = {}
    for bar, sd in zip(bars, sessions):
        session_first_open.setdefault(sd, bar.open)

    vwap: list[float | None] = [None] * n
    bar_in_session: list[int] = [0] * n
    current_session: date | None = None
    cum_pv = 0.0
    cum_vol = 0.0
    counter = 0
    for i, bar in enumerate(bars):
        sd = sessions[i]
        if sd != current_session:
            current_session = sd
            cum_pv = 0.0
            cum_vol = 0.0
            counter = 0
        counter += 1
        bar_in_session[i] = counter
        volume = max(1.0, volumes[i])
        cum_pv += bar.typical_price * volume
        cum_vol += volume
        vwap[i] = cum_pv / cum_vol

    tracker = _EpisodeTracker(config)
    rows: list[FeatureRow] = []

    for i, bar in enumerate(bars):
        sd = sessions[i]
        prev_sd = previous_session.get(sd)
        if timeframe == "1d":
            prior_close = closes[i - 1] if i > 0 else None
        else:
            prior_close = (
                session_last_close.get(prev_sd) if prev_sd is not None else None
            )

        if prior_close and prior_close > 0:
            gap = (session_first_open[sd] - prior_close) / prior_close * 100.0
        else:
            gap = 0.0

        ref_high = prior_highs[i]
        drawdown_high = (
            (ref_high - bar.low) / ref_high * 100.0 if ref_high else 0.0
        )
        close_drawdown_high = (
            (ref_high - bar.close) / ref_high * 100.0 if ref_high else 0.0
        )
        drawdown_prior_close = (
            (prior_close - bar.close) / prior_close * 100.0 if prior_close else 0.0
        )
        rolling_low = rolling_lows[i]
        low_idx = rolling_low_idx[i]
        runup = (
            (bar.close - rolling_low) / rolling_low * 100.0 if rolling_low else 0.0
        )

        state = tracker.update(
            i,
            bar,
            prior_high=ref_high,
            prior_close=prior_close,
        )

        ctx = (daily_context or {}).get(sd) or _default_context(sd)

        ema9_val = ema9[i]
        ema21_val = ema21[i]
        ema50_val = ema50[i]
        rsi_val = rsi14[i]
        atr_val = atr14[i]
        vwap_val = vwap[i]
        vol_ratio = (
            volumes[i] / volume_mean[i - 1]
            if i > 0 and volume_mean[i - 1] and volume_mean[i - 1] > 0
            else 1.0
        )
        dollar_avg = (
            dollar_mean[i - 1]
            if i > 0 and dollar_mean[i - 1] is not None
            else (dollar_volumes[i] if i == 0 else sum(dollar_volumes[:i]) / i)
        )
        realized = realized_vol[i] or 0.0

        prior_vwap = vwap[i - 1] if i > 0 else None
        prior_close_price = closes[i - 1] if i > 0 else None
        same_session_as_prior = i > 0 and sessions[i - 1] == sd
        ema9_cross_up = bool(
            ema9_val is not None
            and i > 0
            and prior_close_price is not None
            and ema9[i - 1] is not None
            and bar.close > ema9_val
            and prior_close_price <= ema9[i - 1]
        )
        rsi_cross_up_30 = bool(
            rsi_val is not None
            and i > 0
            and rsi14[i - 1] is not None
            and rsi_val > 30
            and rsi14[i - 1] <= 30
        )
        rsi_cross_up_40 = bool(
            rsi_val is not None
            and i > 0
            and rsi14[i - 1] is not None
            and rsi_val > 40
            and rsi14[i - 1] <= 40
        )
        vwap_cross_up = bool(
            vwap_val is not None
            and prior_vwap is not None
            and same_session_as_prior
            and bar.close > vwap_val
            and prior_close_price is not None
            and prior_close_price <= prior_vwap
        )

        rows.append(
            FeatureRow(
                index=i,
                ts=bar.ts,
                session=sd,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=volumes[i],
                prior_close=prior_close,
                gap_pct=gap,
                minutes_since_open=session_minutes(bar),
                session_progress=session_progress(bar),
                bar_in_session=bar_in_session[i],
                ema9=ema9_val,
                ema21=ema21_val,
                ema50=ema50_val,
                rsi14=rsi_val,
                rsi_cross_up_30=rsi_cross_up_30,
                rsi_cross_up_40=rsi_cross_up_40,
                atr14=atr_val,
                atr_pct=(atr_val / bar.close * 100.0) if atr_val else 0.0,
                realized_vol_pct=realized * 100.0,
                volume_ratio20=vol_ratio,
                dollar_volume20=dollar_avg or 0.0,
                session_vwap=vwap_val,
                price_vs_vwap_pct=(
                    (bar.close / vwap_val - 1.0) * 100.0 if vwap_val else 0.0
                ),
                price_vs_ema9_pct=(
                    (bar.close / ema9_val - 1.0) * 100.0 if ema9_val else 0.0
                ),
                close_above_vwap=bool(vwap_val is not None and bar.close > vwap_val),
                close_above_ema9=bool(ema9_val is not None and bar.close > ema9_val),
                rolling_high=ref_high,
                rolling_low=rolling_low,
                drawdown_from_high_pct=drawdown_high,
                close_drawdown_from_high_pct=close_drawdown_high,
                drawdown_from_prior_close_pct=drawdown_prior_close,
                runup_from_low_pct=runup,
                bars_since_low=i - low_idx,
                last_swing_low=last_swing_low[i],
                prev_swing_low=prev_swing_low[i],
                last_swing_high=last_swing_high[i],
                prev_swing_high=prev_swing_high[i],
                higher_low=bool(
                    last_swing_low[i] is not None
                    and prev_swing_low[i] is not None
                    and last_swing_low[i] > prev_swing_low[i]
                ),
                lower_high=bool(
                    last_swing_high[i] is not None
                    and prev_swing_high[i] is not None
                    and last_swing_high[i] < prev_swing_high[i]
                ),
                close_above_prior_swing_high=bool(
                    last_swing_high[i] is not None
                    and bar.close > last_swing_high[i]
                ),
                episode_id=state.episode_id if state.episode_id else None,
                episode_active=state.active,
                episode_start_index=state.start_index,
                episode_reference_high=(
                    state.reference_high if state.episode_id else None
                ),
                episode_low=state.low if state.episode_id else None,
                episode_low_index=state.low_index if state.episode_id else None,
                episode_depth_pct=(
                    (state.reference_high - state.low)
                    / state.reference_high
                    * 100.0
                    if state.reference_high and state.low
                    else 0.0
                ),
                episode_recovery_pct=(
                    (bar.close / state.low - 1.0) * 100.0 if state.low else 0.0
                ),
                bars_since_episode_low=(
                    i - state.low_index if state.episode_id else 0
                ),
                attempt_number=state.attempt_number if state.active else 1,
                failed_bounces=state.failed_bounces if state.active else 0,
                failed_bounces_1pct=(
                    state.failed_bounces_1pct if state.active else 0
                ),
                first_bounce_failed=bool(
                    state.active and state.failed_bounces_1pct >= 1
                ),
                bounce_speed_pct_per_bar=(
                    runup / max(1, i - low_idx) if state.active else 0.0
                ),
                green_bar=bar.close > bar.open,
                close_above_prior_high=bool(
                    i > 0 and bar.close > bars[i - 1].high
                ),
                ema9_cross_up=ema9_cross_up,
                vwap_cross_up=vwap_cross_up,
                new_low_recent=bool(
                    state.active and i - state.last_new_low_index <= 2
                ),
                daily_trend_score=ctx.trend_score,
                daily_above_sma50=ctx.above_sma50,
                daily_above_sma200=ctx.above_sma200,
                daily_sma50_gt_sma200=ctx.sma50_gt_sma200,
                daily_return_6m_pct=ctx.return_6m_pct,
                daily_distance_sma50_pct=ctx.distance_sma50_pct,
                daily_atr_pct=ctx.atr14_pct,
                daily_range_5pct_days=ctx.range_5pct_days_60d,
                daily_dip_count_60d=ctx.dip_count_60d,
                daily_avg_dollar_volume=ctx.avg_dollar_volume_60d,
                daily_max_drawdown_1y_pct=ctx.max_drawdown_1y_pct,
                daily_last_return_pct=ctx.last_return_pct,
                daily_two_day_return_pct=ctx.two_day_return_pct,
                daily_last_range_pct=ctx.last_range_pct,
            )
        )

    # If the data ends mid-episode, keep a final record for reporting.
    if tracker.state.active:
        state = tracker.state
        tracker.episodes.append(
            EpisodeRecord(
                episode_id=state.episode_id,
                start_ts=state.start_ts,  # type: ignore[arg-type]
                end_ts=None,
                reference_high=state.reference_high,
                low=state.low,
                low_ts=state.low_ts,  # type: ignore[arg-type]
                depth_pct=(state.reference_high - state.low)
                / state.reference_high
                * 100.0,
                failed_bounces=state.failed_bounces,
                failed_bounces_1pct=state.failed_bounces_1pct,
                recovered=False,
                duration_bars=len(bars) - 1 - (state.start_index or 0),
                max_bounce_pct=state.max_bounce_pct,
            )
        )

    return FeatureSeries(
        symbol=resolved_symbol,
        timeframe=timeframe,
        rows=rows,
        episodes=tracker.episodes,
        bars_per_day=bpd,
    )


def daily_context_map(
    daily_bars: list[Bar],
    *,
    intraday_sessions: list[date] | None = None,
    include_current_day_for_daily: bool = False,
) -> dict[date, DailyContext]:
    """Build point-in-time daily contexts.

    For an intraday session D, the context is computed from daily bars strictly
    before D (``include_current_day_for_daily=False``).  For a daily study the
    current bar is included because the signal is evaluated at that bar's close.
    """

    from .daily import build_daily_contexts

    return build_daily_contexts(
        daily_bars,
        intraday_sessions=intraday_sessions,
        include_current_day=include_current_day_for_daily,
    )
