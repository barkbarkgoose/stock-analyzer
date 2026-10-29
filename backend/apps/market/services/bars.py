"""Incremental, cached bar ingestion.

The cache is the whole point: Yahoo will not serve 5-minute bars older than ~60
days, so the service keeps every bar it has ever fetched.  A request only asks
the provider for ranges that are not already covered.  Re-running an analysis is
therefore cheap and never repeats a historical request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from django.db.models import Count, F, Max, Min

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.types import TIMEFRAME_MINUTES, Bar as EngineBar

from ..models import Bar, DataCoverage, FetchLog, Security
from .providers import get_market_provider, provider_key, provider_warnings


class IngestionError(RuntimeError):
    pass


@dataclass(slots=True)
class CoverageResult:
    security: Security
    timeframe: str
    bars: list[EngineBar] = field(default_factory=list)
    fetched: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    provider: str = ""
    coverage: dict[str, Any] = field(default_factory=dict)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_security(symbol: str, *, create: bool = True) -> Security:
    symbol = symbol.upper().strip()
    if not symbol:
        raise IngestionError("Symbol is required.")
    if create:
        security, _ = Security.objects.get_or_create(symbol=symbol)
        return security
    try:
        return Security.objects.get(symbol=symbol)
    except Security.DoesNotExist as exc:
        raise IngestionError(f"Unknown symbol {symbol}.") from exc


def coverage_snapshot(coverage: DataCoverage | None) -> dict[str, Any]:
    if coverage is None:
        return {}
    return {
        "timeframe": coverage.timeframe,
        "earliest_ts": coverage.earliest_ts.isoformat() if coverage.earliest_ts else None,
        "latest_ts": coverage.latest_ts.isoformat() if coverage.latest_ts else None,
        "unavailable_before": (
            coverage.unavailable_before.isoformat()
            if coverage.unavailable_before
            else None
        ),
        "bar_count": coverage.bar_count,
        "provider": coverage.provider,
        "last_attempt_at": (
            coverage.last_attempt_at.isoformat() if coverage.last_attempt_at else None
        ),
        "last_success_at": (
            coverage.last_success_at.isoformat() if coverage.last_success_at else None
        ),
        "last_error": coverage.last_error,
    }


def _overlap_for(timeframe: str) -> timedelta:
    minutes = TIMEFRAME_MINUTES.get(timeframe)
    if minutes is None:
        return timedelta(days=1)
    return timedelta(minutes=max(5, minutes * 2))


def _upsert_bars(
    security: Security,
    timeframe: str,
    bars: Iterable[EngineBar],
    source: str,
) -> int:
    rows = [
        Bar(
            security=security,
            timeframe=timeframe,
            ts=_utc(bar.ts),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=max(0, int(bar.volume)),
            source=source or bar.source,
        )
        for bar in bars
    ]
    if not rows:
        return 0
    # De-duplicate within the batch; the provider may return an overlap.
    by_ts = {row.ts: row for row in rows}
    rows = [by_ts[ts] for ts in sorted(by_ts)]
    try:
        Bar.objects.bulk_create(
            rows,
            batch_size=2000,
            update_conflicts=True,
            unique_fields=["security", "timeframe", "ts"],
            update_fields=["open", "high", "low", "close", "volume", "source"],
        )
    except Exception:
        # Older SQLite builds lack ON CONFLICT DO UPDATE support.  This path is
        # slow but correct and only used as a fallback.
        for row in rows:
            Bar.objects.update_or_create(
                security=security,
                timeframe=timeframe,
                ts=row.ts,
                defaults={
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "source": row.source,
                },
            )
    if rows:
        Security.objects.filter(pk=security.pk).update(
            data_version=F("data_version") + 1
        )
        security.refresh_from_db(fields=["data_version"])
    return len(rows)


def _update_coverage(
    coverage: DataCoverage,
    *,
    provider: str,
    unavailable_before: datetime | None,
) -> None:
    agg = Bar.objects.filter(
        security=coverage.security, timeframe=coverage.timeframe
    ).aggregate(earliest=Min("ts"), latest=Max("ts"), count=Count("id"))
    coverage.earliest_ts = agg["earliest"]
    coverage.latest_ts = agg["latest"]
    coverage.bar_count = agg["count"] or 0
    coverage.provider = provider
    coverage.last_attempt_at = datetime.now(timezone.utc)
    coverage.last_success_at = coverage.last_attempt_at
    coverage.last_error = ""
    if unavailable_before is not None:
        if (
            coverage.unavailable_before is None
            or unavailable_before > coverage.unavailable_before
        ):
            coverage.unavailable_before = unavailable_before
    coverage.save()


def _missing_ranges(
    coverage: DataCoverage,
    start: datetime,
    end: datetime,
    timeframe: str,
    force: bool,
) -> list[tuple[datetime, datetime]]:
    if force or coverage.latest_ts is None or coverage.bar_count == 0:
        return [(start, end)]

    ranges: list[tuple[datetime, datetime]] = []
    if start < coverage.earliest_ts:
        allowed_start = start
        if (
            coverage.unavailable_before is not None
            and allowed_start < coverage.unavailable_before
        ):
            allowed_start = coverage.unavailable_before
        if allowed_start < coverage.earliest_ts:
            ranges.append((allowed_start, min(end, coverage.earliest_ts)))

    if end > coverage.latest_ts:
        overlap = _overlap_for(timeframe)
        ranges.append((max(start, coverage.latest_ts - overlap), end))

    # Preserve order and remove empty ranges.
    return [(a, b) for a, b in ranges if a < b]


def ensure_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    force: bool = False,
    source: str | None = None,
) -> CoverageResult:
    start = _utc(start)
    end = _utc(end)
    if start >= end:
        raise IngestionError("start must be before end")

    security = get_security(symbol)
    coverage, _ = DataCoverage.objects.get_or_create(
        security=security, timeframe=timeframe
    )
    provider = get_market_provider(source)
    key = provider_key(provider)
    warnings = provider_warnings(provider, timeframe)

    # Never mix bars from different providers/feeds in one cache.  Switching
    # source (including synthetic -> real) resets this timeframe so the profile
    # cannot silently use stale synthetic or differently-adjusted bars.
    if coverage.bar_count > 0 and coverage.provider and coverage.provider != key:
        previous = coverage.provider
        Bar.objects.filter(security=security, timeframe=timeframe).delete()
        coverage.earliest_ts = None
        coverage.latest_ts = None
        coverage.unavailable_before = None
        coverage.bar_count = 0
        coverage.provider = ""
        coverage.save()
        Security.objects.filter(pk=security.pk).update(
            data_version=F("data_version") + 1
        )
        security.refresh_from_db(fields=["data_version"])
        warnings.append(
            f"Provider changed from {previous} to {key}; reset cached {timeframe} "
            f"bars for {security.symbol} and refetching."
        )

    # Avoid hammering a failing provider.  A forced refresh bypasses this.
    if (
        not force
        and coverage.last_error
        and coverage.last_attempt_at
        and (datetime.now(timezone.utc) - coverage.last_attempt_at).total_seconds() < 30
    ):
        return CoverageResult(
            security=security,
            timeframe=timeframe,
            warnings=warnings + ["Skipping provider request after a recent error."],
            error=coverage.last_error,
            provider=provider.name,
            coverage=coverage_snapshot(coverage),
        )

    ranges = _missing_ranges(coverage, start, end, timeframe, force)
    total_fetched = 0
    errors: list[str] = []
    for range_start, range_end in ranges:
        requested_at = time.monotonic()
        try:
            fetched = provider.fetch_bars(symbol, timeframe, range_start, range_end)
            rows = _upsert_bars(security, timeframe, fetched, provider.name)
            total_fetched += rows
            duration_ms = int((time.monotonic() - requested_at) * 1000)
            FetchLog.objects.create(
                security=security,
                timeframe=timeframe,
                source=provider.name,
                requested_start=range_start,
                requested_end=range_end,
                rows=rows,
                status="success" if rows else "empty",
                duration_ms=duration_ms,
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary
            duration_ms = int((time.monotonic() - requested_at) * 1000)
            errors.append(str(exc))
            FetchLog.objects.create(
                security=security,
                timeframe=timeframe,
                source=provider.name,
                requested_start=range_start,
                requested_end=range_end,
                rows=0,
                status="error",
                error=str(exc),
                duration_ms=duration_ms,
            )
            coverage.last_attempt_at = datetime.now(timezone.utc)
            coverage.last_error = str(exc)[:2000]
            coverage.save(update_fields=["last_attempt_at", "last_error"])
            break

    oldest = provider.oldest_available(timeframe)
    unavailable_before = oldest if oldest is not None and start < oldest else None
    if oldest is not None and start < oldest:
        warnings.append(
            f"{provider.name} cannot serve {timeframe} bars before "
            f"{oldest.date().isoformat()}; requesting from the earliest available."
        )
    if not errors:
        _update_coverage(
            coverage,
            provider=key,
            unavailable_before=unavailable_before,
        )

    bars = read_bars(security, timeframe, start=start, end=end)
    return CoverageResult(
        security=security,
        timeframe=timeframe,
        bars=bars,
        fetched=total_fetched,
        warnings=warnings,
        error="; ".join(errors),
        provider=provider.name,
        coverage=coverage_snapshot(coverage),
    )


def read_bars(
    security: Security,
    timeframe: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> list[EngineBar]:
    qs = Bar.objects.filter(security=security, timeframe=timeframe)
    if start is not None:
        qs = qs.filter(ts__gte=_utc(start))
    if end is not None:
        qs = qs.filter(ts__lte=_utc(end))
    if limit is not None:
        rows = list(qs.order_by("-ts")[:limit])
        rows.reverse()
    else:
        rows = list(qs.order_by("ts"))
    return [
        EngineBar(
            symbol=security.symbol,
            ts=row.ts,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            timeframe=row.timeframe,
            source=row.source or "",
        )
        for row in rows
    ]


def coverage_for(symbol: str, timeframes: Iterable[str] | None = None) -> dict[str, Any]:
    security = get_security(symbol, create=False)
    qs = DataCoverage.objects.filter(security=security)
    if timeframes:
        qs = qs.filter(timeframe__in=list(timeframes))
    return {
        "symbol": security.symbol,
        "data_version": security.data_version,
        "coverage": {row.timeframe: coverage_snapshot(row) for row in qs},
    }


def ensure_daily_and_intraday(
    symbol: str,
    config: AnalysisConfig,
    *,
    source: str | None = None,
    force: bool = False,
) -> tuple[list[EngineBar], list[EngineBar], dict[str, Any]]:
    now = datetime.now(timezone.utc)
    daily_start = now - timedelta(days=config.daily_history_days)
    intraday_start = now - timedelta(days=config.intraday_history_days)

    daily_result = ensure_bars(
        symbol, "1d", daily_start, now, force=force, source=source
    )
    if daily_result.error:
        raise IngestionError(f"Daily data fetch failed: {daily_result.error}")
    if not daily_result.bars:
        raise IngestionError(f"No daily bars available for {symbol}.")

    intraday_bars: list[EngineBar] = []
    intraday_result: CoverageResult | None = None
    warnings = list(daily_result.warnings)
    if config.timeframe != "1d":
        try:
            intraday_result = ensure_bars(
                symbol,
                config.timeframe,
                intraday_start,
                now,
                force=force,
                source=source,
            )
            warnings.extend(intraday_result.warnings)
            if intraday_result.error:
                warnings.append(
                    f"Intraday fetch failed, falling back to daily: {intraday_result.error}"
                )
            else:
                intraday_bars = intraday_result.bars
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Intraday fetch failed, falling back to daily: {exc}")

    provider = get_market_provider(source)
    data_info: dict[str, Any] = {
        "daily_source": daily_result.provider,
        "intraday_source": intraday_result.provider if intraday_result else None,
        "requested_timeframe": config.timeframe,
        "provider": provider.describe(),
        "coverage": {
            "1d": daily_result.coverage,
            config.timeframe: (
                intraday_result.coverage if intraday_result else None
            ),
        },
        "warnings": warnings,
    }
    return daily_result.bars, intraday_bars, data_info


def refresh_latest(
    symbol: str,
    config: AnalysisConfig,
    *,
    source: str | None = None,
    intraday_days: int = 5,
) -> CoverageResult:
    """Incrementally fetch only the most recent window for live checks."""

    now = datetime.now(timezone.utc)
    timeframe = config.timeframe
    if timeframe == "1d":
        start = now - timedelta(days=10)
    else:
        start = now - timedelta(days=intraday_days)
    return ensure_bars(symbol, timeframe, start, now, source=source)
