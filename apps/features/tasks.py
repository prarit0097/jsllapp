import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.market.market_time import market_state

from .services import compute_latest_missing

logger = logging.getLogger(__name__)


def _should_run():
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    state = market_state(timezone.now().astimezone(tz))
    return state == 'OPEN'


@shared_task
def compute_scores_task():
    if not _should_run():
        return 'skip'
    try:
        result = compute_latest_missing()
        if result is None:
            return 'no_data'
        return 'ok'
    except Exception as exc:
        logger.exception('compute_scores_task failed: %s', exc)
        return 'error'
