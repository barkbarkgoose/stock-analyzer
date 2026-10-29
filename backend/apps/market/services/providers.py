"""Provider construction and provider-specific caveats."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings

from stock_rebound_analyzer.providers import (
    DataProvider,
    ProviderConfigError,
    ProviderError,
    get_provider as engine_get_provider,
)


class MarketDataError(RuntimeError):
    pass


def get_market_provider(source: str | None = None) -> DataProvider:
    name = (source or settings.MARKET_PROVIDER or "auto").strip().lower()
    try:
        return engine_get_provider(
            name,
            path=settings.MARKET_CSV_PATH or None,
        )
    except (ProviderConfigError, ProviderError) as exc:
        raise MarketDataError(str(exc)) from exc


def provider_key(provider: DataProvider) -> str:
    """Stable cache key for a provider configuration.

    Bars from different providers (or different Alpaca feeds / CSV files) must
    not be mixed in one cache.  The key is stored on DataCoverage and a change
    triggers a clean re-fetch for that symbol/timeframe.
    """

    if provider.name == "alpaca":
        return f"alpaca:{(getattr(provider, 'feed', '') or 'default')[:9]}"
    if provider.name == "csv":
        path = str(getattr(provider, "path", ""))
        digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:7]
        return f"csv:{digest}"
    return provider.name[:16]


def provider_warnings(provider: DataProvider, timeframe: str) -> list[str]:
    warnings: list[str] = []
    if provider.name == "yahoo" and timeframe in {"1m", "5m", "15m", "30m"}:
        warnings.append(
            "Yahoo intraday history is limited (roughly 60 days for 5m, 7 days "
            "for 1m). Cached bars are kept, so longer history accumulates as you "
            "refresh. For multi-month intraday research use Alpaca."
        )
    if provider.name == "alpaca":
        feed = getattr(provider, "feed", "")
        if feed == "iex":
            warnings.append(
                "Alpaca is using the IEX feed. IEX is not consolidated, so "
                "volume/spread-dependent results are approximate. Set "
                "ALPACA_FEED=sip if your plan includes it."
            )
    if provider.name == "synthetic":
        warnings.append(
            "Synthetic data is for demo/testing only; it is not real market data."
        )
    return warnings


def provider_info(provider: DataProvider) -> dict[str, Any]:
    return dict(provider.describe())
