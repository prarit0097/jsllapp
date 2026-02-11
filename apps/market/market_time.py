from datetime import time
from zoneinfo import ZoneInfo

from django.conf import settings


MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def market_state(now_ist):
    if now_ist.weekday() >= 5:
        return 'CLOSED'
    if MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE:
        return 'OPEN'
    return 'CLOSED'


def is_near_close(now_ist):
    return MARKET_CLOSE >= now_ist.time() >= time(15, 20)


def compute_thresholds(now_ist):
    min_candles_60m = 45
    freshness_sec = 180
    if market_state(now_ist) == 'OPEN' and is_near_close(now_ist):
        freshness_sec = 300
    return freshness_sec, min_candles_60m


def is_within_today_session_end(last_candle_dt):
    if not last_candle_dt:
        return False
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    local_dt = last_candle_dt.astimezone(tz)
    session_end = local_dt.replace(
        hour=MARKET_CLOSE.hour,
        minute=MARKET_CLOSE.minute,
        second=0,
        microsecond=0,
    )
    return local_dt.date() == session_end.date() and local_dt <= session_end