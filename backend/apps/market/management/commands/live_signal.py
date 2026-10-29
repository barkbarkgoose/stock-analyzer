import json

from django.core.management.base import BaseCommand, CommandError

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.live import build_live_read

from apps.market.services.bars import (
    ensure_daily_and_intraday,
    get_security,
    read_bars,
)
from apps.market.services.profiles import (
    ProfileBuildError,
    build_profile_for_symbol,
    get_latest_profile,
    get_recommended_context,
)


class Command(BaseCommand):
    help = "Show the current signal read for one symbol (no paper trade)."

    def add_arguments(self, parser):
        parser.add_argument("symbol")
        parser.add_argument("--source", default=None)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        symbol = options["symbol"].upper()
        profile = get_latest_profile(symbol, source=options["source"])
        if profile is None:
            try:
                profile = build_profile_for_symbol(symbol, source=options["source"])
            except ProfileBuildError as exc:
                raise CommandError(str(exc)) from exc
        config = AnalysisConfig.from_dict(profile.get("config"))
        ensure_daily_and_intraday(symbol, config, source=options["source"])
        security = get_security(symbol)
        daily = read_bars(security, "1d", limit=500)
        bars = read_bars(security, config.timeframe, limit=2000)
        context = get_recommended_context(symbol, source=options["source"])
        live = build_live_read(
            symbol=symbol,
            daily_bars=daily,
            bars=bars,
            config=config,
            model_spec=context.get("model_spec"),
            fast_spec=context.get("fast_spec"),
            recommended_rule_id=context.get("recommended_rule_id"),
        )
        if options["json"]:
            self.stdout.write(json.dumps(live, indent=2, sort_keys=True))
            return
        read = live["signal_read"]
        self.stdout.write(f"{symbol}: {read['state']} - {read['detail']}")
        if read.get("waiting_for"):
            self.stdout.write("waiting for: " + "; ".join(read["waiting_for"]))
        self.stdout.write(
            f"prob={read.get('probability')} fast_prob={read.get('probability_fast')}"
        )
        self.stdout.write(f"levels={read.get('levels')}")
        self.stdout.write(f"fake_rebound_risk={read.get('fake_rebound_risk')}")
