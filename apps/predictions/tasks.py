import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.market.market_time import market_state
from .services import generate_latest_predictions, _models_are_fresh

logger = logging.getLogger('apps')


@shared_task
def prediction_task():
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    now_ist = timezone.now().astimezone(tz)
    if market_state(now_ist) != 'OPEN':
        logger.info('Prediction task skipped: market closed')
        return {'skipped': True, 'reason': 'market_closed'}

    try:
        cache_fresh = _models_are_fresh()
        preds = generate_latest_predictions()
        logger.info(
            'Prediction task completed: generated=%s cache=%s',
            len(preds),
            'hit' if cache_fresh else 'miss',
        )
        return {'status': 'ok', 'generated': len(preds), 'cache': 'hit' if cache_fresh else 'miss'}
    except Exception:  # pragma: no cover
        logger.exception('Prediction task failed')
        return {'status': 'error'}
