import logging
from datetime import time
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def is_market_open(current_time=None):
    market_tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    now = current_time or timezone.now().astimezone(market_tz)
    if now.weekday() >= 5:
        return False
    start = time(9, 15)
    end = time(15, 30)
    return start <= now.time() <= end


@shared_task
def ingest_1m_task():
    try:
        if not is_market_open():
            logger.info('Market closed. Skipping ingestion.')
            return 'market_closed'

        from apps.market.providers.yfinance_download_provider import (
            YFinanceDownloadProvider,
        )
        from apps.market.providers.yfinance_provider import YFinanceHistoryProvider
        from apps.market.services import ingest_1m_candles_multi

        primary = YFinanceHistoryProvider()
        fallback = YFinanceDownloadProvider()
        run = ingest_1m_candles_multi(primary, fallback)
        logger.info(
            'Ingest summary primary_ok=%s fallback_ok=%s saved=%s missing=%s outliers=%s',
            run.primary_ok,
            run.fallback_ok,
            run.candles_saved,
            run.missing_filled,
            run.outliers_rejected,
        )
        return 'ok'
    except Exception as exc:
        logger.exception('Ingest task failed: %s', exc)
        return 'error'