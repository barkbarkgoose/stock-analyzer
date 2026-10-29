"""Universe seeding and symbol search."""

from __future__ import annotations

import csv
from pathlib import Path

from django.conf import settings
from django.db.models import Q

from ..models import Security, UniverseMember

SYNTHETIC_SYMBOLS = (
    "DEMO",
    "SYNTH-UP",
    "SYNTH-FAKE",
    "SYNTH-CLEAN",
    "SYNTH-CHOP",
    "SYNTH-DOWN",
    "SYNTH-QUIET",
)


def seed_universe(path: str | Path | None = None, universe: str = "default") -> int:
    source = Path(path or settings.MARKET_UNIVERSE_PATH)
    if not source.exists():
        raise FileNotFoundError(f"Universe file not found: {source}")
    created = 0
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            _, was_created = UniverseMember.objects.update_or_create(
                universe=universe,
                symbol=symbol,
                defaults={
                    "name": (row.get("name") or "").strip(),
                    "sector": (row.get("sector") or "").strip(),
                    "active": True,
                },
            )
            Security.objects.get_or_create(
                symbol=symbol,
                defaults={
                    "name": (row.get("name") or "").strip(),
                    "exchange": "",
                },
            )
            if was_created:
                created += 1
    return created


def universe_symbols(universe: str = "default", limit: int | None = None) -> list[str]:
    qs = UniverseMember.objects.filter(universe=universe, active=True).order_by("symbol")
    if limit is not None:
        qs = qs[:limit]
    symbols = list(qs.values_list("symbol", flat=True))
    if not symbols and universe == "default":
        # First run: seed from the bundled CSV.
        try:
            seed_universe(universe=universe)
        except FileNotFoundError:
            return []
        qs = UniverseMember.objects.filter(universe=universe, active=True).order_by("symbol")
        if limit is not None:
            qs = qs[:limit]
        symbols = list(qs.values_list("symbol", flat=True))
    return symbols


def search_symbols(query: str, limit: int = 20) -> list[dict[str, object]]:
    query = query.upper().strip()
    if not query:
        return []
    members = list(
        UniverseMember.objects.filter(symbol__startswith=query)
        .order_by("symbol")[:limit]
        .values("symbol", "name", "sector")
    )
    known = {item["symbol"] for item in members}
    local = list(
        Security.objects.filter(Q(symbol__startswith=query) | Q(name__icontains=query))
        .order_by("symbol")[:limit]
        .values("symbol", "name", "exchange")
    )
    out: list[dict[str, object]] = []
    for symbol in SYNTHETIC_SYMBOLS:
        if symbol.startswith(query):
            out.append(
                {
                    "symbol": symbol,
                    "name": "Synthetic demo",
                    "sector": "Synthetic",
                    "in_database": Security.objects.filter(symbol=symbol).exists(),
                }
            )
    for item in members:
        out.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "sector": item["sector"],
                "in_database": Security.objects.filter(symbol=item["symbol"]).exists(),
            }
        )
    for item in local:
        if item["symbol"] in known:
            continue
        out.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "sector": "",
                "in_database": True,
            }
        )
    # Always allow the raw query as a direct symbol.
    if query not in {item["symbol"] for item in out} and len(query) <= 12:
        out.insert(
            0,
            {
                "symbol": query,
                "name": "Direct symbol",
                "sector": "",
                "in_database": Security.objects.filter(symbol=query).exists(),
            },
        )
    return out[:limit]
