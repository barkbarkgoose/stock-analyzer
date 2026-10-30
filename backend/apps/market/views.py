"""Market research API.

Every endpoint requires a logged-in user (the DRF default, IsAuthenticated with
JWT).  Analyses trigger provider fetches and CPU-heavy builds, so they must not
be reachable anonymously once the app is on the public internet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.utils import timezone as django_timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from stock_rebound_analyzer.config import AnalysisConfig, config_schema
from stock_rebound_analyzer.profile import ENGINE_VERSION
from stock_rebound_analyzer.live import build_live_read
from stock_rebound_analyzer.types import SUPPORTED_TIMEFRAMES

from .models import AnalysisProfile, PaperTrade, ScreenRun, WatchlistItem
from .serializers import (
    AnalyzeSerializer,
    ChartQuerySerializer,
    IngestSerializer,
    LiveCheckSerializer,
    PaperTickSerializer,
    PaperTradeSerializer,
    ScreenRunSerializer,
    ScreenStartSerializer,
    WatchlistItemSerializer,
    WatchlistSerializer,
)
from .services.bars import (
    IngestionError,
    coverage_for,
    ensure_bars,
    get_security,
    read_bars,
    refresh_latest,
)
from .services.paper import (
    close_trade_manual,
    paper_stats,
    paper_tick,
)
from .services.profiles import (
    ProfileBuildError,
    build_profile_for_symbol,
    context_from_profile,
    get_latest_profile,
    profile_summary,
)
from .services.providers import (
    MarketDataError,
    get_market_provider,
    provider_info,
    provider_warnings,
)
from .services.screener import run_screen_sync, start_screen_run
from .services.universe import search_symbols, universe_symbols


def _config_from(payload: Any) -> AnalysisConfig:
    try:
        return AnalysisConfig.from_dict(payload or {})
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _iso(value):
    return value.isoformat() if value else None


class ConfigView(APIView):

    def get(self, request):
        try:
            provider = get_market_provider()
            info = provider_info(provider)
            warnings = provider_warnings(provider, "5m")
        except MarketDataError as exc:
            info = {"name": "unavailable", "error": str(exc)}
            warnings = [str(exc)]
        try:
            universe_size = len(universe_symbols())
        except Exception:  # noqa: BLE001
            universe_size = 0
        return Response(
            {
                "defaults": AnalysisConfig().as_dict(),
                "schema": config_schema(),
                "timeframes": list(SUPPORTED_TIMEFRAMES),
                "provider": info,
                "provider_warnings": warnings,
                "settings": {
                    "default_notional": settings.MARKET_DEFAULT_NOTIONAL,
                    "paper_enabled": settings.MARKET_PAPER_ENABLED,
                    "screen_default_limit": settings.MARKET_SCREEN_DEFAULT_LIMIT,
                },
                "universe_size": universe_size,
                "disclaimer": (
                    "Historical research only. This tool does not place orders."
                ),
            }
        )


class SymbolSearchView(APIView):

    def get(self, request):
        query = request.query_params.get("q", "")
        return Response({"results": search_symbols(query)})


class AnalyzeView(APIView):

    def post(self, request):
        serializer = AnalyzeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        config = _config_from(data.get("config"))
        try:
            result = build_profile_for_symbol(
                data["symbol"],
                config,
                force=data.get("force", False),
                source=data.get("source") or None,
            )
        except (ProfileBuildError, IngestionError, MarketDataError) as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result)


class ProfileView(APIView):

    def get(self, request, symbol: str):
        config_hash = request.query_params.get("config_hash")
        qs = AnalysisProfile.objects.select_related("security").filter(
            security__symbol=symbol.upper(),
            status="completed",
            engine_version=ENGINE_VERSION,
        )
        if config_hash:
            qs = qs.filter(config_hash=config_hash)
        profile = qs.order_by("-updated_at").first()
        if profile is None:
            raise NotFound("No cached profile. Run an analysis first.")
        result = dict(profile.result)
        result["cache"] = {
            "cached": True,
            "data_version": profile.data_version,
            "built_at": _iso(profile.built_at),
        }
        return Response(result)


class CoverageView(APIView):

    def get(self, request, symbol: str):
        timeframe = request.query_params.get("timeframe", "5m")
        try:
            return Response(coverage_for(symbol, ["1d", timeframe]))
        except IngestionError as exc:
            raise NotFound(str(exc)) from exc


class IngestView(APIView):

    def post(self, request):
        serializer = IngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = datetime.now(timezone.utc)
        end = data.get("end") or now
        timeframe = data["timeframe"]
        if data.get("start"):
            start = data["start"]
        else:
            days = data.get("days") or (1100 if timeframe == "1d" else 60)
            start = end - timedelta(days=days)
        try:
            result = ensure_bars(
                data["symbol"],
                timeframe,
                start,
                end,
                force=data.get("force", False),
                source=data.get("source") or None,
            )
        except (IngestionError, MarketDataError) as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "symbol": data["symbol"],
                "timeframe": timeframe,
                "fetched": result.fetched,
                "bars": len(result.bars),
                "warnings": result.warnings,
                "error": result.error,
                "coverage": result.coverage,
                "provider": result.provider,
            }
        )


class ChartView(APIView):

    def get(self, request, symbol: str):
        serializer = ChartQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            security = get_security(symbol, create=False)
        except IngestionError as exc:
            raise NotFound(str(exc)) from exc
        bars = read_bars(
            security,
            data["timeframe"],
            start=data.get("start"),
            end=data.get("end"),
            limit=data["limit"],
        )
        return Response(
            {
                "symbol": security.symbol,
                "timeframe": data["timeframe"],
                "bars": [
                    {
                        "ts": _iso(bar.ts),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ],
            }
        )


class WatchlistView(APIView):

    def get(self, request):
        items = WatchlistItem.objects.select_related("security").all()
        return Response({"items": WatchlistItemSerializer(items, many=True).data})

    def post(self, request):
        serializer = WatchlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        security = get_security(data["symbol"])
        item, _ = WatchlistItem.objects.update_or_create(
            security=security,
            defaults={
                "active": True,
                "note": data.get("note", ""),
                "config_hash": data.get("config_hash", ""),
            },
        )
        return Response(
            WatchlistItemSerializer(item).data, status=status.HTTP_201_CREATED
        )


class WatchlistDetailView(APIView):

    def delete(self, request, symbol: str):
        deleted, _ = WatchlistItem.objects.filter(
            security__symbol=symbol.upper()
        ).delete()
        if not deleted:
            raise NotFound("Not on watchlist.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class LiveCheckView(APIView):

    def post(self, request):
        serializer = LiveCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        symbol = data["symbol"]
        config = _config_from(data.get("config"))
        source = data.get("source") or None
        profile = get_latest_profile(symbol, source=source)
        if (
            profile is None
            or (profile.get("meta") or {}).get("config_hash") != config.hash
        ):
            try:
                profile = build_profile_for_symbol(
                    symbol, config, source=source
                )
            except (ProfileBuildError, IngestionError, MarketDataError) as exc:
                raise ValidationError(str(exc)) from exc
        profile_config = AnalysisConfig.from_dict(profile.get("config"))
        try:
            refresh_latest(symbol, profile_config, source=data.get("source") or None)
        except (IngestionError, MarketDataError) as exc:
            raise ValidationError(str(exc)) from exc
        security = get_security(symbol)
        now = datetime.now(timezone.utc)
        daily_bars = read_bars(
            security, "1d", start=now - timedelta(days=500)
        )
        if profile_config.timeframe == "1d":
            live_bars = daily_bars
        else:
            live_bars = read_bars(
                security,
                profile_config.timeframe,
                start=now - timedelta(days=25),
            )
        context = context_from_profile(profile)
        live = build_live_read(
            symbol=symbol,
            daily_bars=daily_bars,
            bars=live_bars,
            config=profile_config,
            model_spec=context.get("model_spec"),
            fast_spec=context.get("fast_spec"),
            recommended_rule_id=context.get("recommended_rule_id"),
        )
        watch = WatchlistItem.objects.filter(security=security).first()
        if watch is not None:
            watch.last_checked_at = django_timezone.now()
            watch.last_price = live["signal_read"].get("price")
            watch.last_signal = live["signal_read"]
            watch.config_hash = profile_config.hash
            watch.save(
                update_fields=[
                    "last_checked_at",
                    "last_price",
                    "last_signal",
                    "config_hash",
                    "updated_at",
                ]
            )
        return Response(
            {
                "symbol": symbol,
                "signal_read": live["signal_read"],
                "profile_summary": profile_summary(profile),
                "config": profile_config.as_dict(),
                "warnings": profile.get("warnings", []),
                "data_version": security.data_version,
            }
        )


class ScreenStartView(APIView):

    def post(self, request):
        serializer = ScreenStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        config = _config_from(data.get("config"))
        symbols = [s.upper().strip() for s in data.get("symbols") or [] if s.strip()]
        if not symbols:
            symbols = universe_symbols(
                data.get("universe", "default"),
                limit=data.get("limit") or settings.MARKET_SCREEN_DEFAULT_LIMIT,
            )
        if not symbols:
            raise ValidationError("No symbols to screen.")
        source = data.get("source") or None
        with_intraday = data.get("with_intraday", False)
        if data.get("sync"):
            run = ScreenRun.objects.create(
                status="running",
                config=config.as_dict(),
                symbols=symbols,
                total=len(symbols),
                with_intraday=with_intraday,
                source=source or "",
                started_at=django_timezone.now(),
            )
            results = run_screen_sync(
                symbols, config, source=source, with_intraday=with_intraday
            )
            run.status = "completed"
            run.completed = len(symbols)
            run.results = results
            run.finished_at = django_timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "completed",
                    "results",
                    "finished_at",
                ]
            )
        else:
            try:
                run = start_screen_run(
                    symbols=symbols,
                    config=config,
                    source=source,
                    with_intraday=with_intraday,
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        return Response(
            ScreenRunSerializer(run).data, status=status.HTTP_202_ACCEPTED
        )


class ScreenRunView(APIView):

    def get(self, request, pk: int):
        try:
            run = ScreenRun.objects.get(pk=pk)
        except ScreenRun.DoesNotExist as exc:
            raise NotFound("Screen run not found.") from exc
        if (
            run.status == "running"
            and run.started_at
            and (django_timezone.now() - run.started_at).total_seconds() > 3600
        ):
            run.status = "failed"
            run.error = "Screen run timed out (the server may have restarted)."
            run.finished_at = django_timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
        return Response(ScreenRunSerializer(run).data)


class ScreenLatestView(APIView):

    def get(self, request):
        runs = ScreenRun.objects.order_by("-created_at")[:10]
        return Response(
            {
                "runs": [
                    {
                        "id": run.pk,
                        "status": run.status,
                        "total": run.total,
                        "completed": run.completed,
                        "with_intraday": run.with_intraday,
                        "created_at": _iso(run.created_at),
                        "finished_at": _iso(run.finished_at),
                    }
                    for run in runs
                ]
            }
        )


class UniverseView(APIView):

    def get(self, request):
        universe = request.query_params.get("universe", "default")
        return Response({"universe": universe, "symbols": universe_symbols(universe)})


class PaperTickView(APIView):

    def post(self, request):
        serializer = PaperTickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = paper_tick(
                [s.upper().strip() for s in data.get("symbols") or []] or None,
                config=_config_from(data.get("config")),
                source=data.get("source") or None,
                notional=data.get("notional"),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result)


class PaperTradesView(APIView):

    def get(self, request):
        qs = PaperTrade.objects.select_related("security").all()
        status_filter = request.query_params.get("status")
        if status_filter in {"open", "closed"}:
            qs = qs.filter(status=status_filter)
        limit = min(500, max(1, int(request.query_params.get("limit", 200))))
        return Response(
            {"trades": PaperTradeSerializer(qs[:limit], many=True).data}
        )


class PaperStatsView(APIView):

    def get(self, request):
        return Response(paper_stats())


class PaperCloseView(APIView):

    def post(self, request, pk: int):
        try:
            trade = PaperTrade.objects.get(pk=pk)
        except PaperTrade.DoesNotExist as exc:
            raise NotFound("Paper trade not found.") from exc
        price = request.data.get("price")
        trade = close_trade_manual(
            trade, float(price) if price is not None else None
        )
        return Response(PaperTradeSerializer(trade).data)
