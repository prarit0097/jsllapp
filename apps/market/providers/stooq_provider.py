import csv
import io
from datetime import datetime

import requests
from django.utils import timezone

from .base import BasePriceProvider
from .errors import ProviderError


class StooqProvider(BasePriceProvider):
    def __init__(self, symbol='aapl.us'):
        self.symbol = symbol

    def fetch_latest_1m(self):
        url = f"https://stooq.com/q/d/l/?s={self.symbol}&i=5"
        try:
            response = requests.get(url, timeout=10)
        except Exception as exc:
            raise ProviderError(f"stooq request failed: {exc}")

        if response.status_code != 200:
            raise ProviderError(f"stooq bad status: {response.status_code}")

        content = response.text.strip()
        if not content:
            raise ProviderError('stooq returned empty data')

        reader = csv.DictReader(io.StringIO(content))
        candles = []
        for row in reader:
            date_str = row.get('Date')
            time_str = row.get('Time')
            if not date_str:
                continue
            if time_str:
                ts = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            else:
                ts = datetime.strptime(date_str, "%Y-%m-%d")
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts)
            candles.append(
                {
                    'ts': ts,
                    'open': float(row.get('Open', 0) or 0),
                    'high': float(row.get('High', 0) or 0),
                    'low': float(row.get('Low', 0) or 0),
                    'close': float(row.get('Close', 0) or 0),
                    'volume': float(row.get('Volume', 0) or 0),
                    'source': 'fallback',
                }
            )

        if not candles:
            raise ProviderError('stooq returned no usable rows')

        candles.sort(key=lambda c: c['ts'])
        return candles