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
        ann_result = fetch_announcements_nse()
        parsed = ann_result['parsed_count']
        created = ann_result['saved_count']
        updated = ann_result['updated_count']
        skipped = ann_result['skipped_duplicates']
        parse_errors = ann_result['parse_errors']
        errors = ann_result['errors']

        run.announcements_fetched = created
        run.announcements_ok = (parsed > 0 or created > 0) and not errors
        if errors:
            notes.append(f"announcements_error: {','.join(errors)}")
        notes.append(
            f"ann_parsed={parsed}, ann_created={created}, ann_updated={updated}, ann_skipped={skipped}, ann_parse_errors={parse_errors}"
        )
    except Exception as exc:
        notes.append(f"announcements_error: {exc}")
        logger.exception('Announcements fetch failed: %s', exc)

    run.finished_at = timezone.now()
    run.notes = '; '.join(notes)
    run.save()
    return 'ok'
