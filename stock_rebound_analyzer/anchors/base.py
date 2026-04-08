from abc import ABC, abstractmethod
from datetime import datetime, time
from typing import Any

from ..models import IntradayBar


class Anchor(ABC):
    @abstractmethod
    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        pass

    @abstractmethod
    def description(self) -> str:
        pass


def _is_new_session(bars: list[IntradayBar], idx: int) -> bool:
    if idx == 0:
        return True
    current = bars[idx].timestamp
    previous = bars[idx - 1].timestamp
    return current.date() != previous.date()


def _session_open_price(bars: list[IntradayBar], idx: int) -> float:
    for i in range(idx, -1, -1):
        if _is_new_session(bars, i):
            return bars[i].open
    return bars[0].open


def _session_close_price(bars: list[IntradayBar], idx: int) -> float:
    if idx == 0:
        return bars[0].open
    if _is_new_session(bars, idx):
        return bars[idx - 1].close
    return bars[idx - 1].close


class PreviousCloseAnchor(Anchor):
    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        if current_idx == 0:
            raise IndexError("No previous bar available")
        return _session_close_price(bars, current_idx)

    def description(self) -> str:
        return "Previous day's closing price"


class CurrentDayOpenAnchor(Anchor):
    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        return _session_open_price(bars, current_idx)

    def description(self) -> str:
        return "Current session's opening price"


class RollingIntradayHighAnchor(Anchor):
    def __init__(self, n_bars: int = 75):
        self.n_bars = n_bars

    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        start = max(0, current_idx - self.n_bars + 1)
        window = bars[start : current_idx + 1]
        return max(b.high for b in window)

    def description(self) -> str:
        return f"Rolling intraday high over last {self.n_bars} bars"


class SessionHighAnchor(Anchor):
    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        for i in range(current_idx, -1, -1):
            if _is_new_session(bars, i):
                session_start = i
                break
        else:
            session_start = 0
        session_bars = bars[session_start : current_idx + 1]
        return max(b.high for b in session_bars)

    def description(self) -> str:
        return "Session high since market open"


class VWAPAnchor(Anchor):
    def get_value(self, bars: list[IntradayBar], current_idx: int) -> float:
        cumulative_tpv = 0.0
        cumulative_volume = 0
        for i in range(current_idx + 1):
            bar = bars[i]
            typical_price = (bar.high + bar.low + bar.close) / 3.0
            cumulative_tpv += typical_price * bar.volume
            cumulative_volume += bar.volume
        if cumulative_volume == 0:
            return bars[current_idx].close
        return cumulative_tpv / cumulative_volume

    def description(self) -> str:
        return "Volume-weighted average price (VWAP)"


_ANCHORS: dict[str, type[Anchor] | dict[str, Any]] = {
    "previous_close": PreviousCloseAnchor,
    "current_day_open": CurrentDayOpenAnchor,
    "rolling_intraday_high": RollingIntradayHighAnchor,
    "session_high": SessionHighAnchor,
    "vwap": VWAPAnchor,
}


def get_anchor(name: str) -> Anchor:
    entry = _ANCHORS.get(name)
    if entry is None:
        raise ValueError(f"Unknown anchor: {name}")
    if isinstance(entry, dict):
        return entry["class"](**entry["kwargs"])
    return entry()


def list_anchors() -> list[str]:
    return list(_ANCHORS.keys())
