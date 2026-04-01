from __future__ import annotations

from .base import DataProvider
from .alpaca import AlpacaDataProvider
from .yahoo import YahooDataProvider


AVAILABLE_PROVIDERS = {
    "alpaca": AlpacaDataProvider,
    "yahoo": YahooDataProvider,
}


def get_provider(name: str | None) -> DataProvider:
    if name is None:
        name = "yahoo"

    provider_cls = AVAILABLE_PROVIDERS.get(name.lower())
    if provider_cls is None:
        available = ", ".join(AVAILABLE_PROVIDERS.keys())
        raise ValueError(f"Unknown data provider '{name}'. Available: {available}")

    return provider_cls()
