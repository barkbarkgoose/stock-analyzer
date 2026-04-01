from __future__ import annotations

import csv
from datetime import date

from .models import DailyBar


REQUIRED_COLUMNS = {"date", "open", "high", "low", "close", "volume"}


def load_bars_from_csv(csv_path: str, symbol: str) -> list[DailyBar]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file is missing a header row.")

        fields = {name.strip().lower() for name in reader.fieldnames}
        missing = REQUIRED_COLUMNS - fields
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

        bars: list[DailyBar] = []
        for row in reader:
            row_symbol = row.get("symbol") or row.get("Symbol") or symbol
            bars.append(
                DailyBar(
                    symbol=str(row_symbol),
                    date=date.fromisoformat(str(row["date"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row["volume"])),
                )
            )

    bars.sort(key=lambda b: b.date)
    return bars
