import random
from datetime import timedelta

from django.utils import timezone

from .base import BasePriceProvider


class MockPriceProvider(BasePriceProvider):
    def fetch_latest_1m(self):
        now = timezone.now().replace(second=0, microsecond=0)
        start = now - timedelta(minutes=4)
        candles = []
        price = random.uniform(100, 200)
        for i in range(5):
            ts = start + timedelta(minutes=i)
            open_price = price
            close_price = open_price + random.uniform(-1.5, 1.5)
            high_price = max(open_price, close_price) + random.uniform(0, 0.8)
            low_price = min(open_price, close_price) - random.uniform(0, 0.8)
            volume = max(0, random.uniform(0, 1000))
            candles.append(
                {
                    'ts': ts,
                    'open': float(open_price),
                    'high': float(high_price),
                    'low': float(low_price),
                    'close': float(close_price),
                    'volume': float(volume),
                    'source': 'mock',
                }
            )
            price = close_price
        return candles