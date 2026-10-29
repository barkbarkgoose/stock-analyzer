import json

from django.core.management.base import BaseCommand, CommandError

from stock_rebound_analyzer.config import AnalysisConfig

from apps.market.services.profiles import ProfileBuildError, build_profile_for_symbol


class Command(BaseCommand):
    help = "Build and print a dip-rebound profile for one symbol."

    def add_arguments(self, parser):
        parser.add_argument("symbol")
        parser.add_argument("--timeframe", default="5m")
        parser.add_argument("--source", default=None)
        parser.add_argument("--config-json", default=None)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        overrides = json.loads(options["config_json"]) if options["config_json"] else {}
        overrides["timeframe"] = options["timeframe"]
        config = AnalysisConfig.from_dict(overrides)
        try:
            profile = build_profile_for_symbol(
                options["symbol"],
                config,
                force=options["force"],
                source=options["source"],
            )
        except ProfileBuildError as exc:
            raise CommandError(str(exc)) from exc
        if options["json"]:
            self.stdout.write(json.dumps(profile, indent=2, sort_keys=True))
            return
        meta = profile["meta"]
        qualification = profile.get("qualification", {})
        self.stdout.write(
            f"\n{meta['symbol']} mode={meta['mode']} bars={meta['bars_analyzed']}"
        )
        self.stdout.write(
            f"Qualification: {qualification.get('status')} score={qualification.get('score')}"
        )
        for reason in qualification.get("reasons", []):
            mark = "PASS" if reason["passed"] else "FAIL"
            self.stdout.write(
                f"  [{mark}] {reason['label']}: {reason['value']} ({reason['target']})"
            )
        recommended = profile.get("recommended")
        if recommended:
            stats = recommended["stats"]
            self.stdout.write(
                f"\nRecommended: {recommended['name']} ({recommended['rule_id']})"
            )
            self.stdout.write(
                f"  {stats['trades']} trades | hit {stats['hit_rate']:.1%} "
                f"[{stats['hit_rate_low']:.1%}-{stats['hit_rate_high']:.1%}] | "
                f"net EV {stats['net_ev_pct']:+.2f}%/trade | "
                f"{stats['trades_per_week']:.2f} trades/wk | "
                f"{stats['weekly_return_pct']:+.2f}%/wk"
            )
            self.stdout.write(
                f"  stop {stats['stop_rate']:.1%} | fast hit {stats['fast_hit_rate']:.1%} | "
                f"median hold {stats['median_holding_minutes']:.0f} market min | "
                f"max DD {stats['max_drawdown_pct']:.1f}%"
            )
            oos = recommended.get("walk_forward_oos")
            if oos:
                self.stdout.write(
                    f"  walk-forward OOS: {oos['trades']} trades, "
                    f"hit {oos['hit_rate']:.1%}, net EV {oos['net_ev_pct']:+.2f}%, "
                    f"{oos['weekly_return_pct']:+.2f}%/wk"
                )
            self.stdout.write(f"  {recommended['selection_reason']}")
        model = profile.get("model", {})
        if model.get("available"):
            self.stdout.write(
                f"\nModel: AUC {model.get('auc')} Brier {model.get('brier')} "
                f"threshold {model.get('recommended_threshold')} "
                f"samples {model.get('samples')}"
            )
            for feature in model.get("features", [])[:6]:
                self.stdout.write(
                    f"  {feature['name']}: {feature['coefficient']:+.2f}"
                )
        else:
            self.stdout.write(f"\nModel unavailable: {model.get('reason')}")
        read = profile.get("signal_read", {})
        self.stdout.write(f"\nCurrent read: {read.get('state')} - {read.get('detail')}")
        if read.get("waiting_for"):
            self.stdout.write("  waiting for: " + "; ".join(read["waiting_for"]))
        risk = read.get("fake_rebound_risk", {})
        if risk:
            self.stdout.write(f"  fake-rebound risk: {risk.get('level')} - {risk.get('detail')}")
        for warning in profile.get("warnings", []):
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))
