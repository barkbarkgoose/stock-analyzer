"""API serializers for market research endpoints."""

from __future__ import annotations

from rest_framework import serializers

from .models import PaperTrade, ScreenRun, Security, WatchlistItem


class AnalyzeSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=24)
    config = serializers.JSONField(required=False)
    force = serializers.BooleanField(default=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=16)

    def validate_symbol(self, value: str) -> str:
        return value.upper().strip()


class IngestSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=24)
    timeframe = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "30m", "1h", "1d"], default="5m"
    )
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    days = serializers.IntegerField(required=False, min_value=1, max_value=5000)
    force = serializers.BooleanField(default=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=16)

    def validate_symbol(self, value: str) -> str:
        return value.upper().strip()


class ChartQuerySerializer(serializers.Serializer):
    timeframe = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "30m", "1h", "1d"], default="5m"
    )
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    limit = serializers.IntegerField(required=False, default=2000, min_value=10, max_value=10000)


class WatchlistSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=24)
    note = serializers.CharField(required=False, allow_blank=True)
    config_hash = serializers.CharField(required=False, allow_blank=True)

    def validate_symbol(self, value: str) -> str:
        return value.upper().strip()


class ScreenStartSerializer(serializers.Serializer):
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=24), required=False
    )
    universe = serializers.CharField(required=False, default="default")
    config = serializers.JSONField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=16)
    with_intraday = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=500)
    sync = serializers.BooleanField(default=False)


class LiveCheckSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=24)
    config = serializers.JSONField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=16)

    def validate_symbol(self, value: str) -> str:
        return value.upper().strip()


class PaperTickSerializer(serializers.Serializer):
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=24), required=False
    )
    config = serializers.JSONField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=16)
    notional = serializers.FloatField(required=False, min_value=100)


class SecuritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Security
        fields = ("symbol", "name", "exchange", "active", "data_version")


class WatchlistItemSerializer(serializers.ModelSerializer):
    security = SecuritySerializer(read_only=True)
    open_trade = serializers.SerializerMethodField()

    class Meta:
        model = WatchlistItem
        fields = (
            "id",
            "security",
            "active",
            "note",
            "config_hash",
            "last_checked_at",
            "last_price",
            "last_signal",
            "open_trade",
            "added_at",
        )

    def get_open_trade(self, obj: WatchlistItem):
        trade = (
            PaperTrade.objects.filter(security=obj.security, status="open")
            .order_by("-entry_ts")
            .first()
        )
        return PaperTradeSerializer(trade).data if trade else None


class PaperTradeSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="security.symbol", read_only=True)

    class Meta:
        model = PaperTrade
        fields = (
            "id",
            "symbol",
            "status",
            "rule_id",
            "config_hash",
            "entry_ts",
            "entry_price",
            "notional",
            "qty",
            "target_price",
            "stop_price",
            "probability",
            "signal",
            "exit_ts",
            "exit_price",
            "exit_reason",
            "return_pct",
            "pnl",
            "created_at",
            "updated_at",
        )


class ScreenRunSerializer(serializers.ModelSerializer):
    progress_pct = serializers.SerializerMethodField()

    class Meta:
        model = ScreenRun
        fields = (
            "id",
            "status",
            "config",
            "symbols",
            "total",
            "completed",
            "progress_pct",
            "with_intraday",
            "source",
            "results",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        )

    def get_progress_pct(self, obj: ScreenRun) -> float:
        return obj.completed / obj.total * 100.0 if obj.total else 0.0
