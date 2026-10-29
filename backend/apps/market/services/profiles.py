"""Profile building and caching."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.profile import ENGINE_VERSION, build_profile

from ..models import AnalysisProfile
from .bars import (
    IngestionError,
    ensure_daily_and_intraday,
    get_security,
)
from .providers import get_market_provider, provider_key


class ProfileBuildError(RuntimeError):
    pass


def _cache_meta(cached: bool, profile: AnalysisProfile, built_at: datetime | None) -> dict[str, Any]:
    return {
        "cached": cached,
        "data_version": profile.data_version,
        "built_at": built_at.isoformat() if built_at else None,
    }


def build_profile_for_symbol(
    symbol: str,
    config: AnalysisConfig | None = None,
    *,
    force: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    config = config or AnalysisConfig()
    security = get_security(symbol)
    source_key = provider_key(get_market_provider(source))

    if not force:
        cached = AnalysisProfile.objects.filter(
            security=security,
            config_hash=config.hash,
            source=source_key,
            engine_version=ENGINE_VERSION,
            data_version=security.data_version,
            status="completed",
        ).first()
        if cached is not None:
            result = dict(cached.result)
            result["cache"] = _cache_meta(True, cached, cached.built_at)
            return result

    try:
        daily_bars, intraday_bars, data_info = ensure_daily_and_intraday(
            security.symbol,
            config,
            source=source,
            force=force,
        )
    except IngestionError as exc:
        raise ProfileBuildError(str(exc)) from exc

    # Ingestion may have advanced data_version; check the cache once more.
    security.refresh_from_db(fields=["data_version"])
    if not force:
        cached = AnalysisProfile.objects.filter(
            security=security,
            config_hash=config.hash,
            source=source_key,
            engine_version=ENGINE_VERSION,
            data_version=security.data_version,
            status="completed",
        ).first()
        if cached is not None:
            result = dict(cached.result)
            result["cache"] = _cache_meta(True, cached, cached.built_at)
            return result

    try:
        result = build_profile(
            symbol=security.symbol,
            daily_bars=daily_bars,
            intraday_bars=intraday_bars,
            config=config,
            data_info=data_info,
        )
    except Exception as exc:  # noqa: BLE001
        AnalysisProfile.objects.update_or_create(
            security=security,
            config_hash=config.hash,
            defaults={
                "config": config.as_dict(),
                "source": source_key,
                "engine_version": ENGINE_VERSION,
                "data_version": security.data_version,
                "status": "failed",
                "mode": config.timeframe,
                "result": {},
                "error": str(exc)[:4000],
                "built_at": datetime.now(timezone.utc),
            },
        )
        raise ProfileBuildError(f"Profile build failed: {exc}") from exc

    built_at = datetime.now(timezone.utc)
    profile, _ = AnalysisProfile.objects.update_or_create(
        security=security,
        config_hash=config.hash,
        defaults={
            "config": config.as_dict(),
            "source": source_key,
            "engine_version": ENGINE_VERSION,
            "data_version": security.data_version,
            "status": "completed",
            "mode": result.get("meta", {}).get("mode", ""),
            "result": result,
            "error": "",
            "built_at": built_at,
        },
    )
    result["cache"] = _cache_meta(False, profile, built_at)
    return result


def get_latest_profile(symbol: str, source: str | None = None) -> dict[str, Any] | None:
    security = get_security(symbol, create=False)
    qs = AnalysisProfile.objects.filter(
        security=security, status="completed", engine_version=ENGINE_VERSION
    )
    if source is not None:
        qs = qs.filter(source=provider_key(get_market_provider(source)))
    profile = qs.order_by("-updated_at").first()
    return profile.result if profile else None


def context_from_profile(result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    model = result.get("model") or {}
    recommended = result.get("recommended") or {}
    return {
        "model_spec": model.get("spec") if model.get("available") else None,
        "fast_spec": (
            (model.get("fast") or {}).get("spec")
            if model.get("available") and model.get("fast")
            else None
        ),
        "recommended_rule_id": recommended.get("rule_id"),
        "use_model_filter": bool(recommended.get("use_model_filter")),
        "threshold": recommended.get("threshold"),
        "config": result.get("config"),
        "profile": result,
    }


def get_recommended_context(symbol: str, source: str | None = None) -> dict[str, Any]:
    """Model spec + recommended rule from the latest profile, if any."""

    return context_from_profile(get_latest_profile(symbol, source=source))


def invalidate_profiles(symbol: str, config_hash: str | None = None) -> int:
    security = get_security(symbol, create=False)
    qs = AnalysisProfile.objects.filter(security=security)
    if config_hash:
        qs = qs.filter(config_hash=config_hash)
    return qs.delete()[0]


def profile_summary(result: dict[str, Any]) -> dict[str, Any]:
    recommended = result.get("recommended") or {}
    stats = recommended.get("stats") or {}
    return {
        "rule_id": recommended.get("rule_id"),
        "name": recommended.get("name"),
        "trades": stats.get("trades"),
        "hit_rate": stats.get("hit_rate"),
        "hit_rate_low": stats.get("hit_rate_low"),
        "hit_rate_high": stats.get("hit_rate_high"),
        "net_ev_pct": stats.get("net_ev_pct"),
        "trades_per_week": stats.get("trades_per_week"),
        "weekly_return_pct": stats.get("weekly_return_pct"),
        "stop_rate": stats.get("stop_rate"),
        "max_drawdown_pct": stats.get("max_drawdown_pct"),
        "fast_hit_rate": stats.get("fast_hit_rate"),
    }
