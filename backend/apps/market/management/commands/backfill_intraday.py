from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from apps.market.models import WatchlistItem
from apps.market.services.bars import ensure_bars


class Command(BaseCommand):
    help = (
        "Fetch the latest intraday window for a list of symbols. Run this daily "
        "(e.g. cron) so the 5m cache grows beyond Yahoo's 60-day limit."
    )

    def add_arguments(self, parser):
        parser.add_argument("--symbols", default=None, help="Comma-separated symbols")
        parser.add_argument("--watchlist", action="store_true")
        parser.add_argument("--timeframe", default="5m")
        parser.add_argument("--days", type=int, default=60)
        parser.add_argument("--source", default=None)

    def handle(self, *args, **options):
        if options["symbols"]:
            symbols = [s.strip().upper() for s in options["symbols"].split(",") if s.strip()]
        elif options["watchlist"]:
            symbols = list(
                WatchlistItem.objects.filter(active=True).values_list(
                    "security__symbol", flat=True
                )
            )
        else:
            symbols = []
        if not symbols:
            self.stdout.write(self.style.WARNING("No symbols selected."))
            return
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=options["days"])
        for symbol in symbols:
            result = ensure_bars(
                symbol,
                options["timeframe"],
                start,
                end,
                source=options["source"],
            )
            self.stdout.write(
                f"{symbol}: fetched={result.fetched} cached={len(result.bars)}"
                + (f" error={result.error}" if result.error else "")
            )
