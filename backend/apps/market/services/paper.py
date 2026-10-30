"""Paper trading: turn the live signal read into simulated fills.

This never contacts a broker.  It is a deterministic simulator that uses the
same cached bars, rules and model spec as the research workbench.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Iterable

from django.conf import settings
from django.utils import timezone as django_timezone

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.live import build_live_read

from ..models import PaperTrade, Security, WatchlistItem
from .bars import (
    get_security,
    read_bars,
    refresh_latest,
)
from .profiles import (
    build_profile_for_symbol,
    get_latest_profile,
    get_recommended_context,
)


def _exit_price(raw: float, config: AnalysisConfig) -> float:
    return raw * (1.0 - config.exit_slippage_bps / 10_000.0)


def evaluate_open_trade(
    trade: PaperTrade,
    bars: list,
    config: AnalysisConfig,
) -> dict[str, Any] | None:
    """Return an exit dict if the trade should close, else None."""

    future = [bar for bar in bars if bar.ts > trade.entry_ts]
    if not future:
        return None
    count = 0
    for bar in future:
        count += 1
        hit_target = bar.high >= trade.target_price
        hit_stop = bar.low <= trade.stop_price
        if bar.open <= trade.stop_price:
            return _close_dict(bar.ts, bar.open, "stop", config)
        if bar.open >= trade.target_price:
            return _close_dict(bar.ts, trade.target_price, "target", config)
        if hit_target and hit_stop:
            return _close_dict(bar.ts, trade.stop_price, "stop", config)
        if hit_stop:
            return _close_dict(bar.ts, trade.stop_price, "stop", config)
        if hit_target:
            return _close_dict(bar.ts, trade.target_price, "target", config)
        if count >= config.max_hold_bars:
            return _close_dict(bar.ts, bar.close, "timeout", config)
    return None


def _close_dict(ts: datetime, raw_price: float, reason: str, config: AnalysisConfig) -> dict[str, Any]:
    return {
        "exit_ts": ts,
        "exit_price": _exit_price(raw_price, config),
        "exit_reason": reason,
    }


def _close_trade(trade: PaperTrade, exit_info: dict[str, Any]) -> PaperTrade:
    trade.exit_ts = exit_info["exit_ts"]
    trade.exit_price = exit_info["exit_price"]
    trade.exit_reason = exit_info["exit_reason"]
    trade.return_pct = (trade.exit_price / trade.entry_price - 1.0) * 100.0
    trade.pnl = (trade.exit_price - trade.entry_price) * trade.qty
    trade.status = "closed"
    trade.save(
        update_fields=[
            "exit_ts",
            "exit_price",
            "exit_reason",
            "return_pct",
            "pnl",
            "status",
            "updated_at",
        ]
    )
    return trade


def _open_trade(
    security: Security,
    read: dict[str, Any],
    config: AnalysisConfig,
    notional: float,
    rule_id: str,
    config_hash: str,
) -> PaperTrade:
    levels = read.get("levels", {})
    entry = float(levels.get("entry_estimate") or read.get("price") or 0)
    if entry <= 0:
        raise ValueError("No usable entry price.")
    target = float(levels.get("target") or entry * (1 + config.target_pct / 100.0))
    stop = float(levels.get("stop") or entry * (1 - config.stop_pct / 100.0))
    qty = notional / entry
    return PaperTrade.objects.create(
        security=security,
        status="open",
        rule_id=rule_id,
        config_hash=config_hash,
        entry_ts=datetime.now(timezone.utc),
        entry_price=entry,
        notional=notional,
        qty=qty,
        target_price=target,
        stop_price=stop,
        probability=read.get("probability"),
        signal=read,
    )


def paper_tick(
    symbols: Iterable[str] | None = None,
    *,
    config: AnalysisConfig | None = None,
    source: str | None = None,
    notional: float | None = None,
) -> dict[str, Any]:
    if not settings.MARKET_PAPER_ENABLED:
        raise ValueError("Paper trading is disabled.")
    notional = notional or settings.MARKET_DEFAULT_NOTIONAL
    actions: list[dict[str, Any]] = []
    if symbols is None:
        symbols = list(
            WatchlistItem.objects.filter(active=True).values_list(
                "security__symbol", flat=True
            )
        )
    symbol_list = [s.upper().strip() for s in symbols if s and s.strip()]

    for symbol in symbol_list:
        security = get_security(symbol)
        profile = get_latest_profile(symbol, source=source)
        if profile is None:
            try:
                profile = build_profile_for_symbol(
                    symbol, config or AnalysisConfig(), source=source
                )
            except Exception as exc:  # noqa: BLE001
                actions.append(
                    {"symbol": symbol, "action": "error", "error": str(exc)}
                )
                continue
        profile_config = AnalysisConfig.from_dict(profile.get("config"))
        context = get_recommended_context(symbol, source=source)
        # None when the profile found no rule worth trusting: the read can then
        # still watch, but never opens a trade.
        recommended_rule_id = context.get("recommended_rule_id")

        try:
            refresh_latest(symbol, profile_config, source=source)
        except Exception as exc:  # noqa: BLE001
            actions.append(
                {"symbol": symbol, "action": "error", "error": str(exc)}
            )
            continue

        open_trade = PaperTrade.objects.filter(
            security=security, status="open"
        ).first()
        bars = read_bars(
            security,
            profile_config.timeframe,
            start=datetime.now(timezone.utc) - timedelta(days=25),
        )
        if open_trade is not None:
            exit_info = evaluate_open_trade(open_trade, bars, profile_config)
            if exit_info:
                _close_trade(open_trade, exit_info)
                actions.append(
                    {
                        "symbol": symbol,
                        "action": "close",
                        "trade_id": open_trade.pk,
                        "exit_reason": open_trade.exit_reason,
                        "return_pct": open_trade.return_pct,
                        "pnl": open_trade.pnl,
                    }
                )
            else:
                actions.append(
                    {
                        "symbol": symbol,
                        "action": "hold",
                        "trade_id": open_trade.pk,
                    }
                )
            continue

        daily_bars = read_bars(
            security,
            "1d",
            start=datetime.now(timezone.utc) - timedelta(days=500),
        )
        if profile_config.timeframe == "1d":
            live_bars = daily_bars
        else:
            live_bars = [
                bar
                for bar in bars
                if bar.timeframe == profile_config.timeframe
            ]
        live = build_live_read(
            symbol=symbol,
            daily_bars=daily_bars,
            bars=live_bars,
            config=profile_config,
            model_spec=context.get("model_spec"),
            fast_spec=context.get("fast_spec"),
            recommended_rule_id=recommended_rule_id,
        )
        read = live["signal_read"]
        watch = WatchlistItem.objects.filter(security=security).first()
        if watch is not None:
            watch.last_checked_at = django_timezone.now()
            watch.last_price = read.get("price")
            watch.last_signal = read
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

        if read.get("state") == "signal" and read.get("recommended_fire"):
            use_filter = bool(context.get("use_model_filter"))
            threshold = context.get("threshold")
            probability = read.get("probability")
            if use_filter and (
                probability is None
                or threshold is None
                or float(probability) < float(threshold)
            ):
                actions.append(
                    {
                        "symbol": symbol,
                        "action": "skip_model_filter",
                        "probability": probability,
                        "threshold": threshold,
                        "read": read,
                    }
                )
                continue
            last_trade = (
                PaperTrade.objects.filter(security=security)
                .order_by("-entry_ts")
                .first()
            )
            if last_trade and (
                datetime.now(timezone.utc) - last_trade.entry_ts
            ).total_seconds() < 1800:
                actions.append(
                    {"symbol": symbol, "action": "skip_cooldown", "read": read}
                )
                continue
            try:
                trade = _open_trade(
                    security,
                    read,
                    profile_config,
                    notional,
                    recommended_rule_id,
                    profile_config.hash,
                )
            except Exception as exc:  # noqa: BLE001
                actions.append(
                    {"symbol": symbol, "action": "error", "error": str(exc)}
                )
                continue
            actions.append(
                {
                    "symbol": symbol,
                    "action": "open",
                    "trade_id": trade.pk,
                    "entry": trade.entry_price,
                    "target": trade.target_price,
                    "stop": trade.stop_price,
                    "probability": trade.probability,
                    "read": read,
                }
            )
        else:
            actions.append(
                {
                    "symbol": symbol,
                    "action": "wait",
                    "state": read.get("state"),
                    "read": read,
                }
            )
    return {
        "actions": actions,
        "open_trades": PaperTrade.objects.filter(status="open").count(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def paper_stats() -> dict[str, Any]:
    closed = list(PaperTrade.objects.filter(status="closed"))
    open_trades = PaperTrade.objects.filter(status="open")
    returns = [t.return_pct for t in closed if t.return_pct is not None]
    pnls = [t.pnl for t in closed if t.pnl is not None]
    wins = sum(1 for value in returns if value > 0)
    by_rule: dict[str, dict[str, Any]] = {}
    for trade in closed:
        bucket = by_rule.setdefault(
            trade.rule_id or "unknown",
            {"trades": 0, "wins": 0, "return_sum": 0.0, "pnl": 0.0},
        )
        bucket["trades"] += 1
        if (trade.return_pct or 0) > 0:
            bucket["wins"] += 1
        bucket["return_sum"] += trade.return_pct or 0.0
        bucket["pnl"] += trade.pnl or 0.0
    for bucket in by_rule.values():
        bucket["win_rate"] = (
            bucket["wins"] / bucket["trades"] if bucket["trades"] else 0.0
        )
        bucket["avg_return_pct"] = (
            bucket["return_sum"] / bucket["trades"] if bucket["trades"] else 0.0
        )
    return {
        "closed_trades": len(closed),
        "open_trades": open_trades.count(),
        "wins": wins,
        "win_rate": wins / len(returns) if returns else 0.0,
        "avg_return_pct": mean(returns) if returns else 0.0,
        "total_return_pct": sum(returns),
        "total_pnl": sum(pnls),
        "by_rule": by_rule,
    }


def close_trade_manual(trade: PaperTrade, price: float | None = None) -> PaperTrade:
    if trade.status != "open":
        return trade
    if price is None:
        security = trade.security
        bars = read_bars(
            security,
            "1d",
            start=datetime.now(timezone.utc) - timedelta(days=10),
        )
        price = bars[-1].close if bars else trade.entry_price
    return _close_trade(
        trade,
        {
            "exit_ts": datetime.now(timezone.utc),
            "exit_price": float(price),
            "exit_reason": "manual",
        },
    )
