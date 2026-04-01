from abc import ABC, abstractmethod

from ..models import DailyBar


class DataProvider(ABC):
    @abstractmethod
    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        pass
