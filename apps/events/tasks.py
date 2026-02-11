import logging
from datetime import time
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import EventsFetchRun
from .services import fetch_news_rss

logger = logging.getLogger(__name__)


def is_market_open(now=None):
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    current = now or timezone.now().astimezone(tz)
    if current.weekday() >= 5:
        return False
    return time(9, 15) <= current.time() <= time(15, 30)


@shared_task
def fetch_events_task():
    run = EventsFetchRun.objects.create()
    notes = []
    try:
        news_count, note = fetch_news_rss()
        run.news_fetched = news_count
        run.news_ok = news_count > 0
        if note:
            notes.append(note)
    except Exception as exc:
        notes.append(f"news_error: {exc}")
        logger.exception('News RSS fetch failed: %s', exc)

    run.finished_at = timezone.now()
    run.notes = '; '.join(notes)
    run.save()
    return 'ok'