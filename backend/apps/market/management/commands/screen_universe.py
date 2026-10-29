from django.core.management.base import BaseCommand, CommandError

from stock_rebound_analyzer.config import AnalysisConfig

from apps.market.services.screener import run_screen_sync
from apps.market.services.universe import universe_symbols


class Command(BaseCommand):
    help = "Screen a universe (daily first, optional intraday confirmation)."

    def add_arguments(self, parser):
        parser.add_argument("--universe", default="default")
        parser.add_argument("--symbols", default=None, help="Comma-separated symbols")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--source", default=None)
        parser.add_argument("--with-intraday", action="store_true")
        parser.add_argument("--timeframe", default="5m")

    def handle(self, *args, **options):
        symbols = (
            [s.strip().upper() for s in options["symbols"].split(",") if s.strip()]
            if options["symbols"]
            else universe_symbols(options["universe"], limit=options["limit"])
        )
        if not symbols:
            raise CommandError("No symbols to screen.")
        config = AnalysisConfig.from_dict({"timeframe": options["timeframe"]})
        self.stdout.write(f"Screening {len(symbols)} symbols...")
        results = run_screen_sync(
            symbols,
            config,
            source=options["source"],
            with_intraday=options["with_intraday"],
        )
        self.stdout.write(
            f"\n{'SYMBOL':10s} {'STATUS':10s} {'SCORE':>6s} {'PRICE':>10s} "
            f"{'RULE':24s} {'TRADES':>6s} {'HIT':>6s} {'WEEKLY':>8s}"
        )
        for item in results:
            recommended = item.get("recommended") or {}
            self.stdout.write(
                f"{item.get('symbol',''):10s} {item.get('status',''):10s} "
                f"{float(item.get('score') or 0):6.1f} "
                f"{float(item.get('price') or 0):10.2f} "
                f"{(recommended.get('rule_id') or ''):24s} "
                f"{recommended.get('trades') or 0:6d} "
                f"{(recommended.get('hit_rate') or 0):6.1%} "
                f"{(recommended.get('weekly_return_pct') or 0):+8.2f}"
            )
            if item.get("error"):
                self.stdout.write(self.style.WARNING(f"  error: {item['error']}"))
