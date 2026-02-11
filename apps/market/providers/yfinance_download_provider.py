import yfinance as yf
from django.conf import settings

from .base import BasePriceProvider
from .errors import ProviderError
from .yfinance_provider import _normalize_candles


class YFinanceDownloadProvider(BasePriceProvider):
    def __init__(self, symbol=None):
        self.symbol = symbol or settings.JSLL_TICKER

    def fetch_latest_1m(self):
        try:
            data = yf.download(
                tickers=self.symbol,
                period='1d',
                interval='1m',
                progress=False,
                threads=False,
                auto_adjust=False,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance download failed: {exc}")

        if data is None or data.empty:
            raise ProviderError('yfinance download returned empty data')

        return _normalize_candles(data, self.symbol, 'fallback')