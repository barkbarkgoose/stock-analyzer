from abc import ABC, abstractmethod

from ..models import DailyBar, IntradayBar


class DataProvider(ABC):
    @abstractmethod
    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        pass

    def fetch_intraday_bars(
        self, symbol: str, granularity: str, start: str, end: str
    ) -> list[IntradayBar]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support intraday bars for granularity '{granularity}'."
        )
