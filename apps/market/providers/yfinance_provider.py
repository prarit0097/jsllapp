from datetime import time
from zoneinfo import ZoneInfo

import yfinance as yf
from django.conf import settings

from .base import BasePriceProvider
from .errors import ProviderError


def _to_float(value):
    if hasattr(value, 'iloc'):
        value = value.iloc[0]
    return float(value)


def _ensure_market_tz_index(data, market_tz):
    idx = data.index
    if idx.tz is None:
        idx = idx.tz_localize(ZoneInfo('UTC'))
    idx = idx.tz_convert(market_tz)
    data = data.copy()
    data.index = idx
    return data


def _filter_market_session(data, start_time, end_time):
    market_times = data.index.time
    mask = (market_times >= start_time) & (market_times <= end_time)
    return data.loc[mask]


class YFinanceProvider(BasePriceProvider):
    def __init__(self, symbol=None):
        self.symbol = symbol or settings.JSLL_TICKER

    def fetch_latest_1m(self):
        try:
            ticker = yf.Ticker(self.symbol)
            data = ticker.history(
                period='1d',
                interval='1m',
                auto_adjust=False,
                actions=False,
                prepost=False,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance failed: {exc}")

        if data is None or data.empty:
            raise ProviderError('yfinance returned empty data')

        market_tz = ZoneInfo(settings.JSLL_MARKET_TZ)
        data = _ensure_market_tz_index(data, market_tz)
        data = _filter_market_session(data, time(9, 15), time(15, 30))

        if data.empty:
            raise ProviderError(
                f"no candles in market session for {self.symbol}"
            )

        candles = []
        for idx, row in data.iterrows():
            ts = idx.to_pydatetime()
            candles.append(
                {
                    'ts': ts,
                    'open': _to_float(row['Open']),
                    'high': _to_float(row['High']),
                    'low': _to_float(row['Low']),
                    'close': _to_float(row['Close']),
                    'volume': _to_float(row['Volume']),
                    'source': 'primary',
                }
            )

        candles.sort(key=lambda c: c['ts'])
        return candles