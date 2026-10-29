"""CSV import provider.

Accepted columns (case-insensitive): timestamp/date/datetime, open, high, low,
close, volume, and optional symbol/timeframe.  A date-only file is daily; a
timestamp file is interpreted as the requested timeframe.  Naive intraday
timestamps are assumed to be New York time, which is the usual convention for
broker exports.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from ..indicators import NY
from ..types import Bar
from .base import DataProvider, ProviderError


def _pick(row: dict[str, str], *names: str) -> str | None:
    lowered = {key.strip().lower(): value for key, value in row.items() if key}
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


class CsvProvider(DataProvider):
    name = "csv"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise ProviderError(f"CSV path does not exist: {self.path}")

    def describe(self) -> dict[str, object]:
        return {"name": "csv", "path": str(self.path)}

    def _file_for(self, symbol: str) -> Path:
        if self.path.is_dir():
            for suffix in (".csv", ".CSV"):
                candidate = self.path / f"{symbol}{suffix}"
                if candidate.exists():
                    return candidate
            raise ProviderError(f"No CSV found for {symbol} in {self.path}")
        return self.path

    def fetch_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        path = self._file_for(symbol)
        bars: list[Bar] = []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ProviderError("CSV is missing a header row.")
            for row in reader:
                row_symbol = _pick(row, "symbol", "ticker") or symbol
                if row_symbol.upper() != symbol.upper() and self.path.is_file():
                    continue
                raw_ts = _pick(row, "timestamp", "datetime", "date", "time")
                if not raw_ts:
                    continue
                try:
                    open_price = float(_pick(row, "open") or "")
                    high = float(_pick(row, "high") or "")
                    low = float(_pick(row, "low") or "")
                    close = float(_pick(row, "close") or "")
                    volume = int(float(_pick(row, "volume", "vol") or 0))
                except (TypeError, ValueError):
                    continue
                ts = self._parse_ts(raw_ts, timeframe)
                if ts is None or ts < start or ts > end:
                    continue
                if timeframe == "1d":
                    ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    local = ts.astimezone(NY)
                    minutes = local.hour * 60 + local.minute
                    if not (9 * 60 + 30 <= minutes < 16 * 60):
                        continue
                try:
                    bars.append(
                        Bar(
                            symbol=symbol.upper(),
                            ts=ts,
                            open=open_price,
                            high=high,
                            low=low,
                            close=close,
                            volume=max(0, volume),
                            timeframe=timeframe,
                            source="csv",
                        )
                    )
                except ValueError:
                    continue
        by_ts = {bar.ts: bar for bar in bars}
        return [by_ts[ts] for ts in sorted(by_ts)]

    @staticmethod
    def _parse_ts(raw: str, timeframe: str) -> datetime | None:
        text = raw.strip()
        if not text:
            return None
        try:
            if len(text) == 10:
                parsed = datetime.strptime(text, "%Y-%m-%d")
                return parsed.replace(tzinfo=timezone.utc)
            normalized = text.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=NY if timeframe != "1d" else timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    parsed = parsed.replace(tzinfo=NY if timeframe != "1d" else timezone.utc)
                    return parsed.astimezone(timezone.utc)
                except ValueError:
                    continue
        return None


__all__ = ["CsvProvider"]
