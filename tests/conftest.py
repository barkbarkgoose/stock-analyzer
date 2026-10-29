from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def session_ts(day: str, minute: int = 0) -> datetime:
    year, month, date = (int(part) for part in day.split("-"))
    base = datetime(year, month, date, 9, 30, tzinfo=NY)
    return (base + timedelta(minutes=minute)).astimezone(timezone.utc)
