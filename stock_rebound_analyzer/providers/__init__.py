"""Data provider factory."""

from __future__ import annotations

import os

from .alpaca import AlpacaProvider
from .base import DataProvider, ProviderConfigError, ProviderError
from .csv import CsvProvider
from .synthetic import SyntheticProvider
from .yahoo import YahooProvider

PROVIDER_NAMES = ("yahoo", "alpaca", "synthetic", "csv")


def get_provider(
    name: str | None = None,
    *,
    path: str | None = None,
    **kwargs: object,
) -> DataProvider:
    """Build a provider from a name or from ``MARKET_PROVIDER``.

    ``auto`` prefers Alpaca when credentials are present, otherwise Yahoo.
    """

    resolved = (name or os.getenv("MARKET_PROVIDER", "auto")).strip().lower()
    if resolved in {"demo", "synth"}:
        resolved = "synthetic"
    if resolved == "auto":
        if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"):
            resolved = "alpaca"
        else:
            resolved = "yahoo"
    if resolved == "yahoo":
        return YahooProvider()
    if resolved == "alpaca":
        return AlpacaProvider(**kwargs)  # type: ignore[arg-type]
    if resolved == "synthetic":
        return SyntheticProvider()
    if resolved == "csv":
        if not path:
            raise ProviderConfigError("CSV provider requires a path.")
        return CsvProvider(path)
    raise ProviderError(
        f"Unknown provider {resolved!r}. Choose one of: {', '.join(PROVIDER_NAMES)}, auto."
    )


__all__ = [
    "AlpacaProvider",
    "CsvProvider",
    "DataProvider",
    "PROVIDER_NAMES",
    "ProviderConfigError",
    "ProviderError",
    "SyntheticProvider",
    "YahooProvider",
    "get_provider",
]
