"""Persistent market data, cached research profiles and paper-trading state."""

from __future__ import annotations

from django.db import models


class Security(models.Model):
    symbol = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=255, blank=True)
    exchange = models.CharField(max_length=32, blank=True)
    active = models.BooleanField(default=True)
    # Bumped whenever new bars arrive.  Cached profiles are keyed by this so a
    # stale analysis is never served after a refresh.
    data_version = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]
        verbose_name_plural = "securities"

    def __str__(self) -> str:
        return self.symbol


class Bar(models.Model):
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="bars"
    )
    timeframe = models.CharField(max_length=4)
    ts = models.DateTimeField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.BigIntegerField(default=0)
    source = models.CharField(max_length=16, blank=True)

    class Meta:
        unique_together = (("security", "timeframe", "ts"),)
        indexes = [
            models.Index(fields=["security", "timeframe", "ts"]),
            models.Index(fields=["timeframe", "ts"]),
        ]
        ordering = ["ts"]

    def __str__(self) -> str:
        return f"{self.security.symbol} {self.timeframe} {self.ts.isoformat()}"


class DataCoverage(models.Model):
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="coverage"
    )
    timeframe = models.CharField(max_length=4)
    earliest_ts = models.DateTimeField(null=True, blank=True)
    latest_ts = models.DateTimeField(null=True, blank=True)
    unavailable_before = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Provider cannot serve data before this timestamp.",
    )
    bar_count = models.PositiveBigIntegerField(default=0)
    provider = models.CharField(max_length=16, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        unique_together = (("security", "timeframe"),)
        ordering = ["security__symbol", "timeframe"]

    def __str__(self) -> str:
        return f"{self.security.symbol} {self.timeframe} coverage"


class FetchLog(models.Model):
    STATUS = (
        ("success", "success"),
        ("empty", "empty"),
        ("error", "error"),
        ("skipped", "skipped"),
    )
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="fetch_logs"
    )
    timeframe = models.CharField(max_length=4)
    source = models.CharField(max_length=16, blank=True)
    requested_start = models.DateTimeField()
    requested_end = models.DateTimeField()
    rows = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.security.symbol} {self.timeframe} {self.status}"


class AnalysisProfile(models.Model):
    STATUS = (
        ("completed", "completed"),
        ("failed", "failed"),
    )
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="profiles"
    )
    config_hash = models.CharField(max_length=32)
    source = models.CharField(max_length=16, blank=True)
    engine_version = models.CharField(max_length=16, blank=True)
    config = models.JSONField(default=dict)
    data_version = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS, default="completed")
    mode = models.CharField(max_length=4, blank=True)
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    built_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("security", "config_hash"),)
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["security", "-updated_at"])]

    def __str__(self) -> str:
        return f"{self.security.symbol} profile {self.config_hash}"


class WatchlistItem(models.Model):
    security = models.OneToOneField(
        Security, on_delete=models.CASCADE, related_name="watchlist_item"
    )
    active = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    config_hash = models.CharField(max_length=32, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_price = models.FloatField(null=True, blank=True)
    last_signal = models.JSONField(default=dict, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["security__symbol"]

    def __str__(self) -> str:
        return f"watch {self.security.symbol}"


class ScreenRun(models.Model):
    STATUS = (
        ("pending", "pending"),
        ("running", "running"),
        ("completed", "completed"),
        ("failed", "failed"),
    )
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    config = models.JSONField(default=dict)
    symbols = models.JSONField(default=list)
    total = models.PositiveIntegerField(default=0)
    completed = models.PositiveIntegerField(default=0)
    with_intraday = models.BooleanField(default=False)
    source = models.CharField(max_length=16, blank=True)
    results = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"screen {self.pk} {self.status}"


class PaperTrade(models.Model):
    STATUS = (
        ("open", "open"),
        ("closed", "closed"),
    )
    EXIT_REASONS = (
        ("target", "target"),
        ("stop", "stop"),
        ("timeout", "timeout"),
        ("manual", "manual"),
        ("end_of_data", "end_of_data"),
    )
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="paper_trades"
    )
    status = models.CharField(max_length=16, choices=STATUS, default="open")
    rule_id = models.CharField(max_length=64, blank=True)
    config_hash = models.CharField(max_length=32, blank=True)
    entry_ts = models.DateTimeField()
    entry_price = models.FloatField()
    notional = models.FloatField(default=10_000.0)
    qty = models.FloatField(default=0.0)
    target_price = models.FloatField()
    stop_price = models.FloatField()
    probability = models.FloatField(null=True, blank=True)
    signal = models.JSONField(default=dict, blank=True)
    exit_ts = models.DateTimeField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    exit_reason = models.CharField(
        max_length=16, choices=EXIT_REASONS, blank=True
    )
    return_pct = models.FloatField(null=True, blank=True)
    pnl = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_ts"]
        indexes = [
            models.Index(fields=["security", "status"]),
            models.Index(fields=["status", "-entry_ts"]),
        ]

    def __str__(self) -> str:
        return f"{self.security.symbol} paper {self.status} {self.entry_ts}"


class UniverseMember(models.Model):
    universe = models.CharField(max_length=64, default="default")
    symbol = models.CharField(max_length=24)
    name = models.CharField(max_length=255, blank=True)
    sector = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("universe", "symbol"),)
        ordering = ["universe", "symbol"]

    def __str__(self) -> str:
        return f"{self.universe}:{self.symbol}"
