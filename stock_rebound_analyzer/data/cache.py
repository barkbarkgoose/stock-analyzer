from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..models import DailyBar, IntradayBar


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "stock_cache.db"


DateLike = date | str
DateTimeLike = date | datetime | str


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class DateTimeRange:
    start: datetime
    end: datetime


class DataCache:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def store_daily_bars(
        self,
        symbol: str,
        bars: Iterable[DailyBar],
        *,
        coverage_start: DateLike | None = None,
        coverage_end: DateLike | None = None,
    ) -> None:
        normalized_symbol = symbol.upper()
        materialized_bars = list(bars)
        coverage = self._resolve_daily_coverage(materialized_bars, coverage_start, coverage_end)

        with self._connect() as connection:
            symbol_id = self._get_symbol_id(connection, normalized_symbol)
            connection.executemany(
                """
                INSERT INTO daily_bars (
                    symbol_id,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol_id, trade_date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
                """,
                [
                    (
                        symbol_id,
                        bar.date.isoformat(),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                    )
                    for bar in materialized_bars
                ],
            )
            if coverage is not None:
                self._merge_daily_coverage(connection, symbol_id, coverage.start, coverage.end)

    def get_daily_bars(self, symbol: str, start: DateLike, end: DateLike) -> list[DailyBar]:
        normalized_symbol = symbol.upper()
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.symbol, d.trade_date, d.open, d.high, d.low, d.close, d.volume
                FROM daily_bars d
                INNER JOIN symbols s ON s.id = d.symbol_id
                WHERE s.symbol = ? AND d.trade_date BETWEEN ? AND ?
                ORDER BY d.trade_date ASC
                """,
                (normalized_symbol, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()

        return [
            DailyBar(
                symbol=row["symbol"],
                date=date.fromisoformat(row["trade_date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            for row in rows
        ]

    def store_intraday_bars(
        self,
        symbol: str,
        granularity: str,
        bars: Iterable[IntradayBar],
        *,
        coverage_start: DateTimeLike | None = None,
        coverage_end: DateTimeLike | None = None,
    ) -> None:
        normalized_symbol = symbol.upper()
        materialized_bars = list(bars)
        coverage = self._resolve_intraday_coverage(
            materialized_bars,
            coverage_start,
            coverage_end,
        )

        with self._connect() as connection:
            symbol_id = self._get_symbol_id(connection, normalized_symbol)
            connection.executemany(
                """
                INSERT INTO intraday_bars (
                    symbol_id,
                    granularity,
                    bar_timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol_id, granularity, bar_timestamp) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
                """,
                [
                    (
                        symbol_id,
                        granularity,
                        _serialize_datetime(bar.timestamp),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                    )
                    for bar in materialized_bars
                ],
            )
            if coverage is not None:
                self._merge_intraday_coverage(
                    connection,
                    symbol_id,
                    granularity,
                    coverage.start,
                    coverage.end,
                )

    def get_intraday_bars(
        self,
        symbol: str,
        granularity: str,
        start: DateTimeLike,
        end: DateTimeLike,
    ) -> list[IntradayBar]:
        normalized_symbol = symbol.upper()
        start_at = _coerce_datetime(start, is_end=False)
        end_at = _coerce_datetime(end, is_end=True)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.symbol, i.bar_timestamp, i.open, i.high, i.low, i.close, i.volume
                FROM intraday_bars i
                INNER JOIN symbols s ON s.id = i.symbol_id
                WHERE s.symbol = ?
                  AND i.granularity = ?
                  AND i.bar_timestamp BETWEEN ? AND ?
                ORDER BY i.bar_timestamp ASC
                """,
                (
                    normalized_symbol,
                    granularity,
                    _serialize_datetime(start_at),
                    _serialize_datetime(end_at),
                ),
            ).fetchall()

        return [
            IntradayBar(
                symbol=row["symbol"],
                timestamp=_deserialize_datetime(row["bar_timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            for row in rows
        ]

    def has_granularity(
        self,
        symbol: str,
        start: DateTimeLike,
        end: DateTimeLike,
        granularity: str,
    ) -> bool:
        return not self.get_missing_intraday_ranges(symbol, granularity, start, end)

    def get_missing_daily_ranges(
        self, symbol: str, start: DateLike, end: DateLike
    ) -> list[DateRange]:
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)
        covered_ranges = self._get_daily_coverage_ranges(symbol, start_date, end_date)

        missing: list[DateRange] = []
        cursor = start_date
        for covered in covered_ranges:
            if covered.end < cursor:
                continue
            if covered.start > cursor:
                missing.append(DateRange(start=cursor, end=min(end_date, covered.start - timedelta(days=1))))
            cursor = max(cursor, covered.end + timedelta(days=1))
            if cursor > end_date:
                break

        if cursor <= end_date:
            missing.append(DateRange(start=cursor, end=end_date))
        return missing

    def get_missing_intraday_ranges(
        self,
        symbol: str,
        granularity: str,
        start: DateTimeLike,
        end: DateTimeLike,
    ) -> list[DateTimeRange]:
        start_at = _coerce_datetime(start, is_end=False)
        end_at = _coerce_datetime(end, is_end=True)
        covered_ranges = self._get_intraday_coverage_ranges(symbol, granularity, start_at, end_at)

        missing: list[DateTimeRange] = []
        cursor = start_at
        for covered in covered_ranges:
            if covered.end < cursor:
                continue
            if covered.start > cursor:
                missing.append(DateTimeRange(start=cursor, end=min(end_at, covered.start)))
            cursor = max(cursor, covered.end)
            if cursor >= end_at:
                break

        if cursor < end_at:
            missing.append(DateTimeRange(start=cursor, end=end_at))
        return missing

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS daily_bars (
                    symbol_id INTEGER NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    PRIMARY KEY (symbol_id, trade_date),
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS intraday_bars (
                    symbol_id INTEGER NOT NULL,
                    granularity TEXT NOT NULL,
                    bar_timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    PRIMARY KEY (symbol_id, granularity, bar_timestamp),
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS daily_coverage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol_id INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS intraday_coverage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol_id INTEGER NOT NULL,
                    granularity TEXT NOT NULL,
                    start_timestamp TEXT NOT NULL,
                    end_timestamp TEXT NOT NULL,
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol_date
                    ON daily_bars(symbol_id, trade_date);
                CREATE INDEX IF NOT EXISTS idx_intraday_bars_symbol_granularity_timestamp
                    ON intraday_bars(symbol_id, granularity, bar_timestamp);
                CREATE INDEX IF NOT EXISTS idx_daily_coverage_symbol_dates
                    ON daily_coverage(symbol_id, start_date, end_date);
                CREATE INDEX IF NOT EXISTS idx_intraday_coverage_symbol_granularity_timestamps
                    ON intraday_coverage(symbol_id, granularity, start_timestamp, end_timestamp);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _get_symbol_id(self, connection: sqlite3.Connection, symbol: str) -> int:
        connection.execute(
            "INSERT INTO symbols(symbol) VALUES (?) ON CONFLICT(symbol) DO NOTHING",
            (symbol,),
        )
        row = connection.execute(
            "SELECT id FROM symbols WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Unable to resolve cache symbol id for {symbol}.")
        return int(row["id"])

    def _resolve_daily_coverage(
        self,
        bars: list[DailyBar],
        coverage_start: DateLike | None,
        coverage_end: DateLike | None,
    ) -> DateRange | None:
        if (coverage_start is None) != (coverage_end is None):
            raise ValueError("coverage_start and coverage_end must be provided together.")
        if coverage_start is not None and coverage_end is not None:
            return DateRange(start=_coerce_date(coverage_start), end=_coerce_date(coverage_end))
        if not bars:
            return None
        dates = sorted(bar.date for bar in bars)
        return DateRange(start=dates[0], end=dates[-1])

    def _resolve_intraday_coverage(
        self,
        bars: list[IntradayBar],
        coverage_start: DateTimeLike | None,
        coverage_end: DateTimeLike | None,
    ) -> DateTimeRange | None:
        if (coverage_start is None) != (coverage_end is None):
            raise ValueError("coverage_start and coverage_end must be provided together.")
        if coverage_start is not None and coverage_end is not None:
            return DateTimeRange(
                start=_coerce_datetime(coverage_start, is_end=False),
                end=_coerce_datetime(coverage_end, is_end=True),
            )
        if not bars:
            return None
        timestamps = sorted(bar.timestamp for bar in bars)
        return DateTimeRange(start=timestamps[0], end=timestamps[-1])

    def _merge_daily_coverage(
        self,
        connection: sqlite3.Connection,
        symbol_id: int,
        start_date: date,
        end_date: date,
    ) -> None:
        merge_start = start_date
        merge_end = end_date
        rows = connection.execute(
            """
            SELECT id, start_date, end_date
            FROM daily_coverage
            WHERE symbol_id = ?
              AND end_date >= ?
              AND start_date <= ?
            ORDER BY start_date ASC
            """,
            (
                symbol_id,
                (start_date - timedelta(days=1)).isoformat(),
                (end_date + timedelta(days=1)).isoformat(),
            ),
        ).fetchall()

        if rows:
            merge_start = min(merge_start, *(date.fromisoformat(row["start_date"]) for row in rows))
            merge_end = max(merge_end, *(date.fromisoformat(row["end_date"]) for row in rows))
            connection.executemany(
                "DELETE FROM daily_coverage WHERE id = ?",
                [(row["id"],) for row in rows],
            )

        connection.execute(
            "INSERT INTO daily_coverage(symbol_id, start_date, end_date) VALUES (?, ?, ?)",
            (symbol_id, merge_start.isoformat(), merge_end.isoformat()),
        )

    def _merge_intraday_coverage(
        self,
        connection: sqlite3.Connection,
        symbol_id: int,
        granularity: str,
        start_at: datetime,
        end_at: datetime,
    ) -> None:
        merge_start = start_at
        merge_end = end_at
        rows = connection.execute(
            """
            SELECT id, start_timestamp, end_timestamp
            FROM intraday_coverage
            WHERE symbol_id = ?
              AND granularity = ?
              AND end_timestamp >= ?
              AND start_timestamp <= ?
            ORDER BY start_timestamp ASC
            """,
            (
                symbol_id,
                granularity,
                _serialize_datetime(start_at),
                _serialize_datetime(end_at),
            ),
        ).fetchall()

        if rows:
            merge_start = min(merge_start, *(_deserialize_datetime(row["start_timestamp"]) for row in rows))
            merge_end = max(merge_end, *(_deserialize_datetime(row["end_timestamp"]) for row in rows))
            connection.executemany(
                "DELETE FROM intraday_coverage WHERE id = ?",
                [(row["id"],) for row in rows],
            )

        connection.execute(
            """
            INSERT INTO intraday_coverage(symbol_id, granularity, start_timestamp, end_timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                symbol_id,
                granularity,
                _serialize_datetime(merge_start),
                _serialize_datetime(merge_end),
            ),
        )

    def _get_daily_coverage_ranges(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[DateRange]:
        normalized_symbol = symbol.upper()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.start_date, c.end_date
                FROM daily_coverage c
                INNER JOIN symbols s ON s.id = c.symbol_id
                WHERE s.symbol = ?
                  AND c.end_date >= ?
                  AND c.start_date <= ?
                ORDER BY c.start_date ASC
                """,
                (normalized_symbol, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()

        return [
            DateRange(
                start=max(start_date, date.fromisoformat(row["start_date"])),
                end=min(end_date, date.fromisoformat(row["end_date"])),
            )
            for row in rows
        ]

    def _get_intraday_coverage_ranges(
        self,
        symbol: str,
        granularity: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[DateTimeRange]:
        normalized_symbol = symbol.upper()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.start_timestamp, c.end_timestamp
                FROM intraday_coverage c
                INNER JOIN symbols s ON s.id = c.symbol_id
                WHERE s.symbol = ?
                  AND c.granularity = ?
                  AND c.end_timestamp >= ?
                  AND c.start_timestamp <= ?
                ORDER BY c.start_timestamp ASC
                """,
                (
                    normalized_symbol,
                    granularity,
                    _serialize_datetime(start_at),
                    _serialize_datetime(end_at),
                ),
            ).fetchall()

        return [
            DateTimeRange(
                start=max(start_at, _deserialize_datetime(row["start_timestamp"])),
                end=min(end_at, _deserialize_datetime(row["end_timestamp"])),
            )
            for row in rows
        ]


def _coerce_date(value: DateLike) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    candidate = value.strip()
    if len(candidate) == 10:
        return date.fromisoformat(candidate)
    return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()


def _coerce_datetime(value: DateTimeLike, *, is_end: bool) -> datetime:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.max if is_end else time.min)

    candidate = value.strip()
    if len(candidate) == 10:
        parsed_date = date.fromisoformat(candidate)
        return datetime.combine(parsed_date, time.max if is_end else time.min)

    parsed_datetime = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    return _normalize_datetime(parsed_datetime)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _serialize_datetime(value: datetime) -> str:
    return _normalize_datetime(value).isoformat(timespec="microseconds")


def _deserialize_datetime(value: str) -> datetime:
    return _normalize_datetime(datetime.fromisoformat(value))
