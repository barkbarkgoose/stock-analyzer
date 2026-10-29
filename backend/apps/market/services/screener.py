"""Daily-first universe screening, with optional intraday confirmation."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from django.db import close_old_connections
from django.utils import timezone as django_timezone

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.daily import build_daily_profile

from ..models import ScreenRun
from .bars import ensure_bars, get_security, read_bars
from .profiles import ProfileBuildError, build_profile_for_symbol, profile_summary
from .universe import universe_symbols

STATUS_RANK = {"qualified": 3, "watch": 2, "reject": 1}


def screen_symbol(
    symbol: str,
    config: AnalysisConfig,
    *,
    source: str | None = None,
    with_intraday: bool = False,
) -> dict[str, Any]:
    symbol = symbol.upper().strip()
    security = get_security(symbol)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=config.daily_history_days)
    result = ensure_bars(symbol, "1d", start, now, source=source)
    if result.error or not result.bars:
        return {
            "symbol": symbol,
            "status": "reject",
            "score": 0,
            "error": result.error or "No daily data.",
            "warnings": result.warnings,
        }
    daily_bars = read_bars(security, "1d", start=start, end=now)
    daily = build_daily_profile(daily_bars, config)
    qualification = daily.get("qualification", {})
    out: dict[str, Any] = {
        "symbol": symbol,
        "status": qualification.get("status", "reject"),
        "score": qualification.get("score", 0),
        "price": daily.get("price"),
        "uptrend": daily.get("uptrend", {}),
        "volatility": daily.get("volatility", {}),
        "dips": {
            key: daily.get("dips", {}).get(key)
            for key in (
                "count",
                "per_month",
                "fake_rebound_rate",
                "recover_1pct_rate",
                "median_days_to_1pct",
                "avg_max_rebound_pct",
            )
        },
        "qualification": qualification,
        "warnings": result.warnings + daily.get("warnings", []),
        "error": "",
    }
    if with_intraday and out["status"] in {"qualified", "watch"}:
        try:
            profile = build_profile_for_symbol(symbol, config, source=source)
            out["recommended"] = profile_summary(profile)
            out["episode_summary"] = profile.get("episode_summary")
            out["readiness"] = profile.get("automation_readiness")
            out["model"] = {
                "available": (profile.get("model") or {}).get("available"),
                "auc": (profile.get("model") or {}).get("auc"),
                "threshold": (profile.get("model") or {}).get("recommended_threshold"),
            }
            out["warnings"].extend(profile.get("warnings", []))
        except ProfileBuildError as exc:
            out["profile_error"] = str(exc)
    return out


def sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            STATUS_RANK.get(str(item.get("status")), 0),
            float(item.get("score") or 0),
            str(item.get("symbol")),
        ),
        reverse=True,
    )


def run_screen_sync(
    symbols: Iterable[str],
    config: AnalysisConfig,
    *,
    source: str | None = None,
    with_intraday: bool = False,
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    symbol_list = [s.upper().strip() for s in symbols if s and s.strip()]
    for index, symbol in enumerate(symbol_list, start=1):
        try:
            item = screen_symbol(
                symbol, config, source=source, with_intraday=with_intraday
            )
        except Exception as exc:  # noqa: BLE001
            item = {
                "symbol": symbol,
                "status": "reject",
                "score": 0,
                "error": str(exc),
                "warnings": [],
            }
        results.append(item)
        if progress:
            progress(index, len(symbol_list), item)
    return sort_results(results)


def _run_thread(run_id: int) -> None:
    close_old_connections()
    try:
        run = ScreenRun.objects.get(pk=run_id)
        run.status = "running"
        run.started_at = django_timezone.now()
        run.save(update_fields=["status", "started_at"])
        config = AnalysisConfig.from_dict(run.config)
        results: list[dict[str, Any]] = []
        total = max(1, run.total)
        for index, symbol in enumerate(run.symbols, start=1):
            try:
                item = screen_symbol(
                    str(symbol),
                    config,
                    source=run.source or None,
                    with_intraday=run.with_intraday,
                )
            except Exception as exc:  # noqa: BLE001
                item = {
                    "symbol": str(symbol),
                    "status": "reject",
                    "score": 0,
                    "error": str(exc),
                    "warnings": [],
                }
            results.append(item)
            ScreenRun.objects.filter(pk=run_id).update(
                completed=index,
                results=sort_results(results),
            )
        ScreenRun.objects.filter(pk=run_id).update(
            status="completed",
            completed=total,
            results=sort_results(results),
            finished_at=django_timezone.now(),
        )
    except Exception as exc:  # noqa: BLE001
        ScreenRun.objects.filter(pk=run_id).update(
            status="failed",
            error=str(exc)[:4000],
            finished_at=django_timezone.now(),
        )
    finally:
        close_old_connections()


def start_screen_run(
    *,
    symbols: Iterable[str] | None = None,
    universe: str = "default",
    config: AnalysisConfig | None = None,
    source: str | None = None,
    with_intraday: bool = False,
    limit: int | None = 25,
) -> ScreenRun:
    config = config or AnalysisConfig()
    symbol_list = [s.upper().strip() for s in (symbols or []) if s and s.strip()]
    if not symbol_list:
        symbol_list = universe_symbols(universe, limit=limit)
    if not symbol_list:
        raise ValueError("No symbols to screen.")
    run = ScreenRun.objects.create(
        status="pending",
        config=config.as_dict(),
        symbols=symbol_list,
        total=len(symbol_list),
        with_intraday=with_intraday,
        source=source or "",
    )
    thread = threading.Thread(target=_run_thread, args=(run.pk,), daemon=True)
    thread.start()
    return run
