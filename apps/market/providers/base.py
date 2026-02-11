from abc import ABC, abstractmethod


class BasePriceProvider(ABC):
    @abstractmethod
    def fetch_latest_1m(self):
        """
        Returns list of candles:
        [
          {
            "ts": datetime,
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
          }
        ]
        """
        raise NotImplementedError