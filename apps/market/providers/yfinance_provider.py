import yfinance as yf
from django.utils import timezone

from .base import BasePriceProvider
from .errors import ProviderError


class YFinanceProvider(BasePriceProvider):
    def __init__(self, symbol='AAPL'):
        self.symbol = symbol

    def fetch_latest_1m(self):
        try:
            data = yf.download(
                tickers=self.symbol,
                period='1d',
                interval='1m',
                progress=False,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance failed: {exc}")

        if data is None or data.empty:
            raise ProviderError('yfinance returned empty data')

        candles = []
        for idx, row in data.iterrows():
            ts = idx.to_pydatetime()
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts)
            candles.append(
                {
                    'ts': ts,
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume']),
                    'source': 'primary',
                }
            )

        candles.sort(key=lambda c: c['ts'])
        return candles