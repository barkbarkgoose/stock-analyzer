"""Daily regime context, qualification and daily dip/recovery statistics."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date
from statistics import mean, median
from typing import Any

from .bars import normalize_bars
from .config import AnalysisConfig
from .indicators import atr, ema, sma
from .types import Bar, DailyContext


def _pct(numerator: float, denominator: float) -> float:
    return (numerator / denominator - 1.0) * 100.0 if denominator else 0.0


def _max_drawdown(closes: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in closes:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak * 100.0)
    return worst


@dataclass(slots=True)
class _DailyArrays:
    bars: list[Bar]
    dates: list[date]
    closes: list[float]
    highs: list[float]
    lows: list[float]
    volumes: list[float]
    dollar_volumes: list[float]
    sma20: list[float | None]
    sma50: list[float | None]
    sma200: list[float | None]
    atr14: list[float | None]
    ema21: list[float | None]


def _arrays(daily_bars: list[Bar]) -> _DailyArrays:
    bars = normalize_bars(daily_bars, timeframe="1d")
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [float(b.volume) for b in bars]
    return _DailyArrays(
        bars=bars,
        dates=[b.ts.date() for b in bars],
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        dollar_volumes=[b.dollar_volume for b in bars],
        sma20=sma(closes, 20),
        sma50=sma(closes, 50),
        sma200=sma(closes, 200),
        atr14=atr(bars, 14),
        ema21=ema(closes, 21),
    )


def _context_at(arr: _DailyArrays, index: int) -> DailyContext:
    close = arr.closes[index]
    sma20 = arr.sma20[index]
    sma50 = arr.sma50[index]
    sma200 = arr.sma200[index]
    start_60 = max(0, index - 59)
    window_highs = arr.highs[start_60 : index + 1]
    window_lows = arr.lows[start_60 : index + 1]
    window_closes = arr.closes[start_60 : index + 1]
    window_volumes = arr.dollar_volumes[start_60 : index + 1]
    range_days = sum(
        1
        for h, l, c in zip(window_highs, window_lows, window_closes)
        if c > 0 and (h - l) / c * 100.0 >= 5.0
    )
    close_days = 0
    for j in range(max(1, index - 59), index + 1):
        if arr.closes[j - 1] > 0 and abs(
            (arr.closes[j] / arr.closes[j - 1] - 1.0) * 100.0
        ) >= 5.0:
            close_days += 1
    dip_count = 0
    for j in range(max(1, index - 59), index + 1):
        if arr.closes[j - 1] > 0 and (
            (arr.closes[j - 1] - arr.closes[j]) / arr.closes[j - 1] * 100.0
        ) >= 5.0:
            dip_count += 1

    return_6m = (
        _pct(close, arr.closes[index - 126]) if index >= 126 else 0.0
    )
    return_1y = (
        _pct(close, arr.closes[index - 252]) if index >= 252 else 0.0
    )
    start_1y = max(0, index - 251)
    max_dd = _max_drawdown(arr.closes[start_1y : index + 1])
    atr14 = arr.atr14[index]
    atr_pct = (atr14 / close * 100.0) if atr14 else 0.0
    distance_sma50 = _pct(close, sma50) if sma50 else 0.0

    components = [
        1.0 if sma20 and close > sma20 else 0.0,
        1.0 if sma50 and close > sma50 else 0.0,
        1.0 if sma200 and close > sma200 else 0.0,
        1.0 if sma20 and sma50 and sma20 > sma50 else 0.0,
        1.0 if sma50 and sma200 and sma50 > sma200 else 0.0,
        1.0 if return_6m > 0 else 0.0,
    ]
    trend_score = sum(components) / len(components)
    last_return = (
        _pct(arr.closes[index], arr.closes[index - 1]) if index >= 1 else 0.0
    )
    two_day_return = (
        _pct(arr.closes[index], arr.closes[index - 2]) if index >= 2 else 0.0
    )
    last_range = (
        (arr.highs[index] - arr.lows[index]) / close * 100.0 if close else 0.0
    )
    return DailyContext(
        as_of=arr.dates[index],
        close=close,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        above_sma20=bool(sma20 and close > sma20),
        above_sma50=bool(sma50 and close > sma50),
        above_sma200=bool(sma200 and close > sma200),
        sma50_gt_sma200=bool(sma50 and sma200 and sma50 > sma200),
        return_6m_pct=return_6m,
        return_1y_pct=return_1y,
        distance_sma50_pct=distance_sma50,
        atr14_pct=atr_pct,
        range_5pct_days_60d=range_days,
        close_5pct_days_60d=close_days,
        dip_count_60d=dip_count,
        avg_dollar_volume_60d=mean(window_volumes) if window_volumes else 0.0,
        max_drawdown_1y_pct=max_dd,
        trend_score=trend_score,
        last_return_pct=last_return,
        two_day_return_pct=two_day_return,
        last_range_pct=last_range,
    )


def build_daily_contexts(
    daily_bars: list[Bar],
    *,
    intraday_sessions: list[date] | None = None,
    include_current_day: bool = False,
) -> dict[date, DailyContext]:
    """Point-in-time daily contexts.

    - ``include_current_day=True``: context for a daily bar includes that bar's
      close (used when the daily close is the signal bar).
    - ``include_current_day=False``: context for date D uses only daily bars
      strictly before D.  This is what intraday studies must use.
    """

    arr = _arrays(daily_bars)
    if not arr.bars:
        return {}

    if include_current_day:
        return {
            arr.dates[i]: _context_at(arr, i) for i in range(len(arr.dates))
        }

    if intraday_sessions is not None:
        out: dict[date, DailyContext] = {}
        for session in sorted(set(intraday_sessions)):
            idx = bisect.bisect_left(arr.dates, session) - 1
            if idx >= 0:
                out[session] = _context_at(arr, idx)
        return out

    out = {}
    for i, session in enumerate(arr.dates):
        if i > 0:
            out[session] = _context_at(arr, i - 1)
    return out


def _dip_event(
    arr: _DailyArrays,
    index: int,
    *,
    window: int,
    target_pct: float,
) -> dict[str, Any]:
    entry = arr.closes[index]
    future = list(range(index + 1, min(len(arr.bars), index + 1 + window)))
    if not future:
        return {
            "date": arr.dates[index].isoformat(),
            "dip_pct": 0.0,
            "entry": entry,
            "days_to_1pct": None,
            "days_to_target": None,
            "max_rebound_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "fake_rebound": False,
            "recovered": False,
        }

    dips = (arr.closes[index - 1] - entry) / arr.closes[index - 1] * 100.0
    target = entry * (1.0 + target_pct / 100.0)
    days_to_1pct = None
    days_to_target = None
    max_high = entry
    min_low = entry
    fake = False
    min_low_offset = 0
    min_low_value = entry

    for offset, j in enumerate(future, start=1):
        if days_to_1pct is None and arr.highs[j] >= entry * 1.01:
            days_to_1pct = offset
        if days_to_target is None and arr.highs[j] >= target:
            days_to_target = offset
        max_high = max(max_high, arr.highs[j])
        if arr.lows[j] < min_low_value:
            min_low_value = arr.lows[j]
            min_low_offset = offset
        min_low = min(min_low, arr.lows[j])

    # A fake rebound: price bounced at least 1% from the entry before making a
    # lower low inside the window.
    if min_low_offset > 0:
        pre_low_high = max([arr.highs[index]] + [arr.highs[j] for j in future[:min_low_offset]])
        fake = pre_low_high >= entry * 1.01

    return {
        "date": arr.dates[index].isoformat(),
        "dip_pct": dips,
        "entry": entry,
        "days_to_1pct": days_to_1pct,
        "days_to_target": days_to_target,
        "max_rebound_pct": (max_high / entry - 1.0) * 100.0,
        "max_drawdown_pct": (min_low / entry - 1.0) * 100.0,
        "fake_rebound": fake,
        "recovered": days_to_target is not None,
    }


def build_daily_profile(
    daily_bars: list[Bar], config: AnalysisConfig
) -> dict[str, Any]:
    arr = _arrays(daily_bars)
    if not arr.bars:
        return {
            "bars": 0,
            "start": None,
            "end": None,
            "qualification": {
                "status": "reject",
                "score": 0,
                "reasons": [
                    {
                        "code": "no_data",
                        "label": "Daily history",
                        "passed": False,
                        "value": "0 bars",
                        "target": f">= {config.min_daily_bars} bars",
                    }
                ],
            },
            "uptrend": {},
            "volatility": {},
            "dips": {"events": [], "count": 0},
            "episodes": [],
            "warnings": ["No daily bars available."],
        }

    ctx = _context_at(arr, len(arr.bars) - 1)
    price = ctx.close
    recent = arr.closes[-1]
    reasons: list[dict[str, Any]] = []

    def reason(
        code: str,
        label: str,
        passed: bool,
        value: str,
        target: str,
        detail: str = "",
    ) -> None:
        reasons.append(
            {
                "code": code,
                "label": label,
                "passed": passed,
                "value": value,
                "target": target,
                "detail": detail,
            }
        )

    history_ok = len(arr.bars) >= config.min_daily_bars
    reason(
        "history",
        "Daily history",
        history_ok,
        f"{len(arr.bars)} bars",
        f">= {config.min_daily_bars} bars",
        "A long history is needed to estimate a trend regime.",
    )
    price_ok = price >= config.min_price
    reason(
        "price",
        "Share price",
        price_ok,
        f"${price:,.2f}",
        f">= ${config.min_price:,.2f}",
        "Very low-priced stocks have wider relative spreads and gap risk.",
    )
    dollar_volume = ctx.avg_dollar_volume_60d
    liquidity_ok = dollar_volume >= config.min_dollar_volume
    reason(
        "liquidity",
        "Liquidity",
        liquidity_ok,
        f"${dollar_volume / 1_000_000:,.1f}M/day",
        f">= ${config.min_dollar_volume / 1_000_000:,.1f}M/day",
        "Average 60-day dollar volume.",
    )
    # A dip can put price modestly below SMA50; that is often the opportunity.
    # Require the longer-term trend (SMA50 > SMA200, price > SMA200) and cap how
    # far below SMA50 the pullback is allowed to go.
    above50_ok = bool(
        ctx.above_sma50
        or (ctx.sma50 is not None and ctx.distance_sma50_pct >= -config.max_below_sma50_pct)
    )
    reason(
        "uptrend_sma50",
        "Price near/above 50-day SMA",
        above50_ok,
        f"{price:,.2f} vs {ctx.sma50:,.2f}" if ctx.sma50 else "n/a",
        f">= -{config.max_below_sma50_pct:.1f}% vs SMA50",
        "A dip can dip below SMA50; the longer-term trend is the main filter.",
    )
    sma50_200_ok = ctx.sma50_gt_sma200 if config.uptrend_require_sma50_gt_sma200 else True
    reason(
        "uptrend_sma50_sma200",
        "SMA50 above SMA200",
        sma50_200_ok,
        (
            f"{ctx.sma50:,.2f} vs {ctx.sma200:,.2f}"
            if ctx.sma50 and ctx.sma200
            else "n/a"
        ),
        "SMA50 > SMA200",
        "Medium-term trend is up.",
    )
    above200_ok = ctx.above_sma200 if config.uptrend_require_sma200 else True
    reason(
        "uptrend_sma200",
        "Price above 200-day SMA",
        above200_ok,
        f"{price:,.2f} vs {ctx.sma200:,.2f}" if ctx.sma200 else "n/a",
        "Price > SMA200",
        "Long-term trend filter.",
    )
    return_ok = ctx.return_6m_pct >= config.uptrend_min_6m_return_pct
    reason(
        "uptrend_6m_return",
        "6-month return",
        return_ok,
        f"{ctx.return_6m_pct:+.1f}%",
        f">= {config.uptrend_min_6m_return_pct:+.1f}%",
        "Momentum filter.",
    )
    drawdown_ok = ctx.max_drawdown_1y_pct <= config.max_drawdown_1y_pct
    reason(
        "uptrend_drawdown",
        "1-year max drawdown",
        drawdown_ok,
        f"{ctx.max_drawdown_1y_pct:.1f}%",
        f"<= {config.max_drawdown_1y_pct:.1f}%",
        "Avoid broken trends that keep making lower lows.",
    )
    distance_ok = ctx.distance_sma50_pct <= config.max_distance_from_sma50_pct
    reason(
        "uptrend_extension",
        "Distance above SMA50",
        distance_ok,
        f"{ctx.distance_sma50_pct:+.1f}%",
        f"<= {config.max_distance_from_sma50_pct:.1f}%",
        "Buying a pullback is preferable to buying an extended breakout.",
    )

    range_ok = ctx.range_5pct_days_60d >= config.volatility_min_range_days
    atr_ok = ctx.atr14_pct >= config.volatility_min_atr_pct
    vol_ok = range_ok or atr_ok
    reason(
        "volatility_range",
        "5% intraday range days (60d)",
        range_ok,
        f"{ctx.range_5pct_days_60d} days",
        f">= {config.volatility_min_range_days} days",
        "The stock needs enough intraday movement to offer 1% rebounds.",
    )
    reason(
        "volatility_atr",
        "ATR14 %",
        atr_ok,
        f"{ctx.atr14_pct:.2f}%",
        f">= {config.volatility_min_atr_pct:.2f}%",
        "Alternative volatility measure; either this or range days can qualify.",
    )
    # The user's criterion is >=5% movement within a day or two, which can be
    # an intraday range even when the close-to-close move is smaller. Accept
    # either close-to-close dips or >=5% range days.
    dip_ok = (
        ctx.dip_count_60d >= 1
        or ctx.range_5pct_days_60d >= config.volatility_min_range_days
    )
    reason(
        "dip_frequency",
        "5% dip days (60d)",
        dip_ok,
        f"{ctx.dip_count_60d} close / {ctx.range_5pct_days_60d} range",
        f">= 1 close or >= {config.volatility_min_range_days} range",
        "The stock needs recurring 5% movement to offer dip/rebound trades.",
    )

    hard_fail = not history_ok or not price_ok or not liquidity_ok
    trend_ok = all(
        [above50_ok, sma50_200_ok, above200_ok, return_ok, drawdown_ok, distance_ok]
    )
    score = (
        ctx.trend_score * 40.0
        + min(1.0, ctx.range_5pct_days_60d / max(1, config.volatility_min_range_days * 2))
        * 15.0
        + min(1.0, ctx.atr14_pct / 8.0) * 10.0
        + min(1.0, ctx.dip_count_60d / 4.0) * 15.0
        + min(1.0, dollar_volume / 100_000_000.0) * 10.0
        + max(0.0, 1.0 - ctx.max_drawdown_1y_pct / 60.0) * 10.0
    )
    score = round(min(100.0, max(0.0, score)), 1)
    if hard_fail or not trend_ok:
        status = "reject"
    elif vol_ok and dip_ok and score >= 60:
        status = "qualified"
    else:
        status = "watch"

    events = []
    for i in range(1, len(arr.bars)):
        dip = (arr.closes[i - 1] - arr.closes[i]) / arr.closes[i - 1] * 100.0
        if dip >= config.dip_threshold_pct:
            events.append(
                _dip_event(
                    arr,
                    i,
                    window=config.daily_recovery_window_days,
                    target_pct=config.daily_recovery_target_pct,
                )
            )

    n_events = len(events)
    fake_count = sum(1 for e in events if e["fake_rebound"])
    recover_1pct = sum(1 for e in events if e["days_to_1pct"] is not None)
    recover_target = sum(1 for e in events if e["days_to_target"] is not None)
    days_to_target = [e["days_to_target"] for e in events if e["days_to_target"]]
    days_to_1pct = [e["days_to_1pct"] for e in events if e["days_to_1pct"]]
    max_rebounds = [e["max_rebound_pct"] for e in events]
    max_drawdowns = [e["max_drawdown_pct"] for e in events]
    months = max(1.0, len(arr.bars) / 21.0)
    warnings: list[str] = []
    if len(arr.bars) < config.min_daily_bars:
        warnings.append(
            f"Only {len(arr.bars)} daily bars; {config.min_daily_bars} are recommended for the SMA200 filter."
        )
    if n_events < 5:
        warnings.append(
            "Fewer than 5 daily dip events; daily rebound statistics are noisy."
        )

    return {
        "bars": len(arr.bars),
        "start": arr.dates[0].isoformat(),
        "end": arr.dates[-1].isoformat(),
        "price": price,
        "qualification": {
            "status": status,
            "score": score,
            "reasons": reasons,
            "trend_ok": trend_ok,
            "volatility_ok": vol_ok,
            "dip_ok": dip_ok,
        },
        "uptrend": {
            "sma20": ctx.sma20,
            "sma50": ctx.sma50,
            "sma200": ctx.sma200,
            "above_sma20": ctx.above_sma20,
            "above_sma50": ctx.above_sma50,
            "above_sma200": ctx.above_sma200,
            "sma50_gt_sma200": ctx.sma50_gt_sma200,
            "return_6m_pct": ctx.return_6m_pct,
            "return_1y_pct": ctx.return_1y_pct,
            "distance_sma50_pct": ctx.distance_sma50_pct,
            "max_drawdown_1y_pct": ctx.max_drawdown_1y_pct,
            "trend_score": ctx.trend_score,
        },
        "volatility": {
            "atr14_pct": ctx.atr14_pct,
            "range_5pct_days_60d": ctx.range_5pct_days_60d,
            "close_5pct_days_60d": ctx.close_5pct_days_60d,
            "avg_dollar_volume_60d": dollar_volume,
            "dips_per_month": n_events / months,
        },
        "dips": {
            "count": n_events,
            "per_month": n_events / months,
            "avg_dip_pct": mean([e["dip_pct"] for e in events]) if events else 0.0,
            "fake_rebound_count": fake_count,
            "fake_rebound_rate": fake_count / n_events if n_events else 0.0,
            "recover_1pct_count": recover_1pct,
            "recover_1pct_rate": recover_1pct / n_events if n_events else 0.0,
            "recover_target_count": recover_target,
            "recover_target_rate": recover_target / n_events if n_events else 0.0,
            "median_days_to_1pct": median(days_to_1pct) if days_to_1pct else None,
            "median_days_to_target": median(days_to_target) if days_to_target else None,
            "avg_max_rebound_pct": mean(max_rebounds) if max_rebounds else 0.0,
            "avg_max_drawdown_pct": mean(max_drawdowns) if max_drawdowns else 0.0,
            "events": events[-40:],
        },
        "warnings": warnings,
        "close": recent,
    }


def daily_context_for_sessions(
    daily_bars: list[Bar], sessions: list[date]
) -> dict[date, DailyContext]:
    return build_daily_contexts(
        daily_bars, intraday_sessions=sessions, include_current_day=False
    )
