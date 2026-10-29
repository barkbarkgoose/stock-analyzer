from django.contrib import admin

from .models import (
    AnalysisProfile,
    Bar,
    DataCoverage,
    FetchLog,
    PaperTrade,
    ScreenRun,
    Security,
    UniverseMember,
    WatchlistItem,
)


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "exchange", "active", "data_version", "updated_at")
    search_fields = ("symbol", "name")


@admin.register(DataCoverage)
class DataCoverageAdmin(admin.ModelAdmin):
    list_display = (
        "security",
        "timeframe",
        "bar_count",
        "earliest_ts",
        "latest_ts",
        "provider",
        "last_success_at",
        "last_error",
    )
    list_filter = ("timeframe", "provider")


@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ("security", "timeframe", "status", "rows", "source", "created_at")
    list_filter = ("status", "timeframe", "source")
    search_fields = ("security__symbol",)


@admin.register(AnalysisProfile)
class AnalysisProfileAdmin(admin.ModelAdmin):
    list_display = ("security", "config_hash", "status", "mode", "data_version", "built_at")
    list_filter = ("status", "mode")
    search_fields = ("security__symbol",)


@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ("security", "active", "last_price", "last_checked_at", "added_at")
    search_fields = ("security__symbol",)


@admin.register(ScreenRun)
class ScreenRunAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "total", "completed", "with_intraday", "created_at")
    list_filter = ("status", "with_intraday")


@admin.register(PaperTrade)
class PaperTradeAdmin(admin.ModelAdmin):
    list_display = (
        "security",
        "status",
        "rule_id",
        "entry_ts",
        "entry_price",
        "exit_ts",
        "exit_reason",
        "return_pct",
        "pnl",
    )
    list_filter = ("status", "exit_reason", "rule_id")
    search_fields = ("security__symbol",)


@admin.register(UniverseMember)
class UniverseMemberAdmin(admin.ModelAdmin):
    list_display = ("universe", "symbol", "name", "sector", "active")
    list_filter = ("universe", "active")
    search_fields = ("symbol", "name")


@admin.register(Bar)
class BarAdmin(admin.ModelAdmin):
    list_display = ("security", "timeframe", "ts", "open", "high", "low", "close", "volume")
    list_filter = ("timeframe", "source")
    search_fields = ("security__symbol",)
