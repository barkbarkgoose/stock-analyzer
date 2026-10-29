from django.core.management.base import BaseCommand

from apps.market.services.universe import seed_universe


class Command(BaseCommand):
    help = "Seed the default screening universe from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None)
        parser.add_argument("--universe", default="default")

    def handle(self, *args, **options):
        created = seed_universe(options["path"], universe=options["universe"])
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new symbols."))
