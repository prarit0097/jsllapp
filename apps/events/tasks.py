import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.market.market_time import market_state
from .models import EventsFetchRun
from .services import fetch_announcements_nse, fetch_news_rss

logger = logging.getLogger(__name__)


def _should_run(schedule_type):
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    state = market_state(timezone.now().astimezone(tz))
    return (schedule_type == 'open' and state == 'OPEN') or (schedule_type == 'closed' and state == 'CLOSED')


@shared_task
def fetch_events_task(schedule_type='open'):
    if not _should_run(schedule_type):
        return 'skip'

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

    try:
        ann_count, note = fetch_announcements_nse()
        run.announcements_fetched = ann_count
        run.announcements_ok = ann_count > 0
        if note:
            notes.append(note)
    except Exception as exc:
        notes.append(f"announcements_error: {exc}")
        logger.exception('Announcements fetch failed: %s', exc)

    run.finished_at = timezone.now()
    run.notes = '; '.join(notes)
    run.save()
    return 'ok'