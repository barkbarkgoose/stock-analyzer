"""Standalone CLI for a one-off symbol profile (no cache)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from .config import AnalysisConfig
from .profile import build_profile
from .providers import get_provider


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a dip-rebound profile for one symbol."
    )
    parser.add_argument("symbol", help="Ticker, e.g. AAPL or DEMO")
    parser.add_argument(
        "--provider",
        default="auto",
        help="auto | yahoo | alpaca | synthetic | csv",
    )
    parser.add_argument("--csv", help="CSV path when --provider csv")
    parser.add_argument("--timeframe", default="5m", help="1m|5m|15m|30m|1h|1d")
    parser.add_argument("--config-json", help="JSON object of AnalysisConfig overrides")
    parser.add_argument("--json", action="store_true", help="Print the full profile JSON")
    return parser.parse_args()


def _print_summary(profile: dict) -> None:
    meta = profile.get("meta", {})
    print()
    print(f"{meta.get('symbol')}  mode={meta.get('mode')}  bars={meta.get('bars_analyzed')}")
    qualification = profile.get("qualification", {})
    print(
        "Qualification: "
        f"{qualification.get('status')}  score={qualification.get('score')}"
    )
    for reason in qualification.get("reasons", []):
        mark = "PASS" if reason.get("passed") else "FAIL"
        print(f"  [{mark}] {reason.get('label')}: {reason.get('value')} ({reason.get('target')})")

    recommended = profile.get("recommended")
    if recommended:
        stats = recommended.get("stats", {})
        print()
        print(f"Recommended signal: {recommended.get('name')} ({recommended.get('rule_id')})")
        print(
            f"  {stats.get('trades')} trades | hit {stats.get('hit_rate', 0):.1%} "
            f"[{stats.get('hit_rate_low', 0):.1%}-{stats.get('hit_rate_high', 0):.1%}] "
            f"| net EV {stats.get('net_ev_pct', 0):+.2f}%/trade "
            f"| {stats.get('trades_per_week', 0):.2f} trades/wk "
            f"| {stats.get('weekly_return_pct', 0):+.2f}%/wk"
        )
        print(
            f"  stop rate {stats.get('stop_rate', 0):.1%} | "
            f"2h/fast hit {stats.get('fast_hit_rate', 0):.1%} | "
            f"median hold {stats.get('median_holding_minutes', 0):.0f} market min | "
            f"max DD {stats.get('max_drawdown_pct', 0):.1f}%"
        )
        wf = recommended.get("walk_forward_oos")
        if wf:
            print(
                "  walk-forward OOS: "
                f"{wf.get('trades')} trades, hit {wf.get('hit_rate', 0):.1%}, "
                f"net EV {wf.get('net_ev_pct', 0):+.2f}%, "
                f"{wf.get('weekly_return_pct', 0):+.2f}%/wk"
            )
        print(f"  {recommended.get('selection_reason')}")

    model = profile.get("model", {})
    print()
    if model.get("available"):
        print(
            f"Model: AUC {model.get('auc')} | Brier {model.get('brier')} | "
            f"threshold {model.get('recommended_threshold')} | "
            f"samples {model.get('samples')}"
        )
        top = model.get("features", [])[:5]
        print("  top features: " + ", ".join(f"{f['name']} ({f['coefficient']:+.2f})" for f in top))
    else:
        print(f"Model: unavailable ({model.get('reason')})")

    read = profile.get("signal_read", {})
    print()
    print(f"Current read: {read.get('state')} - {read.get('detail')}")
    if read.get("waiting_for"):
        print("  waiting for: " + "; ".join(read["waiting_for"]))
    if read.get("levels"):
        levels = read["levels"]
        print(
            f"  entry~{levels.get('entry_estimate'):.2f} target {levels.get('target'):.2f} "
            f"stop {levels.get('stop'):.2f}"
        )
    risk = read.get("fake_rebound_risk", {})
    if risk:
        print(f"  fake-rebound risk: {risk.get('level')} - {risk.get('detail')}")

    if profile.get("warnings"):
        print()
        for warning in profile["warnings"]:
            print(f"WARNING: {warning}")


def main() -> None:
    args = _parse_args()
    overrides = json.loads(args.config_json) if args.config_json else {}
    overrides["timeframe"] = args.timeframe
    config = AnalysisConfig.from_dict(overrides)
    provider = get_provider(args.provider, path=args.csv)
    symbol = args.symbol.upper().strip()
    end = datetime.now(timezone.utc)
    daily_start = end - timedelta(days=config.daily_history_days)
    intraday_start = end - timedelta(days=config.intraday_history_days)

    daily = provider.fetch_bars(symbol, "1d", daily_start, end)
    intraday = []
    if config.timeframe != "1d":
        try:
            intraday = provider.fetch_bars(
                symbol, config.timeframe, intraday_start, end
            )
        except Exception as exc:  # noqa: BLE001 - CLI is best-effort
            print(f"Intraday fetch failed, falling back to daily: {exc}")

    profile = build_profile(
        symbol=symbol,
        daily_bars=daily,
        intraday_bars=intraday,
        config=config,
        data_info={
            "daily_source": provider.name,
            "intraday_source": provider.name if intraday else None,
            "provider": provider.describe(),
        },
    )
    if args.json:
        print(json.dumps(profile, indent=2, sort_keys=True))
    else:
        _print_summary(profile)


if __name__ == "__main__":
    main()
