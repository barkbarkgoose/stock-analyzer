import time
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError


from apps.market.services.paper import paper_tick


NY = ZoneInfo("America/New_York")


def market_open() -> bool:
    now = datetime.now(NY)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


class Command(BaseCommand):
    help = "Run one or more simulated paper-trading ticks."

    def add_arguments(self, parser):
        parser.add_argument("--symbols", default=None, help="Comma-separated symbols")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--source", default=None)
        parser.add_argument("--notional", type=float, default=None)
        parser.add_argument("--force-hours", action="store_true")

    def handle(self, *args, **options):
        symbols = (
            [s.strip().upper() for s in options["symbols"].split(",") if s.strip()]
            if options["symbols"]
            else None
        )
        while True:
            if not options["force_hours"] and not market_open():
                self.stdout.write("Market closed; sleeping.")
            else:
                try:
                    result = paper_tick(
                        symbols,
                        source=options["source"],
                        notional=options["notional"],
                    )
                except Exception as exc:  # noqa: BLE001
                    raise CommandError(str(exc)) from exc
                for action in result["actions"]:
                    self.stdout.write(str(action))
            if options["once"]:
                break
            time.sleep(max(10, options["interval"]))
