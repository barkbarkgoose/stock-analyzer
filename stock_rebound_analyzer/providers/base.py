"""Provider interface and shared rate limiting."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..types import Bar


class ProviderError(RuntimeError):
    pass


class ProviderConfigError(ProviderError):
    pass


class RateLimiter:
    """Simple thread-safe token bucket / minimum-interval limiter."""

    def __init__(self, max_calls: int, period_seconds: float, min_interval: float = 0.0):
        self.max_calls = max(1, max_calls)
        self.period_seconds = period_seconds
        self.min_interval = min_interval
        self._calls: list[float] = []
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.period_seconds
            self._calls = [t for t in self._calls if t > cutoff]
            if self._calls:
                if len(self._calls) >= self.max_calls:
                    sleep_for = self.period_seconds - (now - self._calls[0]) + 0.01
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                    now = time.monotonic()
                if self.min_interval > 0:
                    since_last = now - self._last_call
                    if since_last < self.min_interval:
                        time.sleep(self.min_interval - since_last)
                        now = time.monotonic()
            self._calls.append(now)
            self._last_call = now


class DataProvider(ABC):
    name = "base"

    @abstractmethod
    def fetch_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        raise NotImplementedError

    def oldest_available(self, timeframe: str) -> datetime | None:
        return None

    def supports(self, timeframe: str) -> bool:
        return timeframe in {"1m", "5m", "15m", "30m", "1h", "1d"}

    def describe(self) -> dict[str, object]:
        return {"name": self.name}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
