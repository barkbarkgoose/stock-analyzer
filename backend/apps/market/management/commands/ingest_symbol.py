from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.market.services.bars import IngestionError, ensure_bars


class Command(BaseCommand):
    help = "Fetch and cache bars for one symbol (incremental)."

    def add_arguments(self, parser):
        parser.add_argument("symbol")
        parser.add_argument("--timeframe", default="5m")
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--source", default=None)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        timeframe = options["timeframe"]
        days = options["days"] or (1100 if timeframe == "1d" else 60)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        try:
            result = ensure_bars(
                options["symbol"],
                timeframe,
                start,
                end,
                force=options["force"],
                source=options["source"],
            )
        except (IngestionError, Exception) as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"{options['symbol']} {timeframe}: fetched={result.fetched} "
            f"cached={len(result.bars)} provider={result.provider}"
        )
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(warning))
        if result.error:
            raise CommandError(result.error)
