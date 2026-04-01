from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from dotenv import load_dotenv

from .analysis import analyze_dip_rebounds
from .data_loader import load_bars_from_csv
from .data_providers import get_provider


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze dip/rebound behavior for a stock symbol."
    )
    parser.add_argument("--symbol", required=True, help="Ticker symbol, e.g. SUUN")
    parser.add_argument(
        "--start",
        default=(date.today() - timedelta(days=365)).isoformat(),
        help="Start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--end", default=date.today().isoformat(), help="End date YYYY-MM-DD"
    )
    parser.add_argument(
        "--dip-threshold",
        type=float,
        default=5.0,
        help="Dip threshold percent (default: 5)",
    )
    parser.add_argument(
        "--rebound-target",
        type=float,
        default=3.0,
        help="Rebound target percent (default: 3)",
    )
    parser.add_argument(
        "--rebound-window",
        type=int,
        default=5,
        help="Look-ahead window in trading days (default: 5)",
    )
    parser.add_argument("--csv", help="Optional local CSV path to use instead of API")
    parser.add_argument(
        "--show-events",
        type=int,
        default=8,
        help="How many most-recent dip events to print",
    )
    return parser.parse_args()


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _warn_if_small_sample(dip_count: int) -> None:
    if dip_count < 20:
        print("WARNING: Fewer than 20 dip events. Confidence interval may be unstable.")


def main() -> None:
    load_dotenv()
    args = _parse_args()

    symbol = args.symbol.upper().strip()
    dip_threshold = args.dip_threshold / 100
    rebound_target = args.rebound_target / 100

    if args.csv:
        bars = load_bars_from_csv(args.csv, symbol=symbol)
    else:
        data_source = os.getenv("DATA_SOURCE", "yahoo")
        provider = get_provider(data_source)
        bars = provider.fetch_daily_bars(symbol=symbol, start=args.start, end=args.end)

    if len(bars) < args.rebound_window + 2:
        raise SystemExit(
            "Not enough bars to run analysis with the selected rebound window."
        )

    report = analyze_dip_rebounds(
        symbol=symbol,
        bars=bars,
        dip_threshold_pct=dip_threshold,
        rebound_target_pct=rebound_target,
        rebound_window_days=args.rebound_window,
    )

    print()
    print(f"Symbol: {report.symbol}")
    print(f"Date range: {bars[0].date} -> {bars[-1].date}")
    print(f"Bars analyzed: {report.bar_count}")
    print(f"Dip events (>= {args.dip_threshold:.2f}% close drop): {report.dip_count}")
    print(
        f"Rebound target (within {args.rebound_window} days): {args.rebound_target:.2f}%"
    )
    print(f"Successes: {report.success_count}/{report.dip_count}")
    print(f"Success rate: {_format_pct(report.success_rate)}")
    print(
        "95% Wilson CI: "
        f"{_format_pct(report.confidence_low)} to {_format_pct(report.confidence_high)}"
    )
    print(f"Avg max rebound after dip: {_format_pct(report.average_max_return_pct)}")
    print(
        f"Avg worst drawdown after dip: {_format_pct(report.average_worst_drawdown_pct)}"
    )

    _warn_if_small_sample(report.dip_count)

    if report.dip_events:
        print()
        print("Recent dip events:")
        for event in report.dip_events[-args.show_events :]:
            outcome = "HIT" if event.success else "MISS"
            days = (
                str(event.days_to_target) if event.days_to_target is not None else "-"
            )
            print(
                f"- {event.date} | dip={_format_pct(event.dip_pct)} "
                f"max_rebound={_format_pct(event.max_return_pct)} "
                f"drawdown={_format_pct(event.worst_drawdown_pct)} "
                f"days_to_target={days} | {outcome}"
            )


if __name__ == "__main__":
    main()
