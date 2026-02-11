from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Announcement, NewsItem
from .nse import fetch_nse_announcements
from .rss import fetch_feeds
from .sentiment import score_sentiment
from .taxonomy import classify_announcement, compute_dedupe_hash, tag_news


def _ensure_ist(dt):
    if not dt:
        return timezone.now().astimezone(ZoneInfo('Asia/Kolkata'))
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
    return dt.astimezone(ZoneInfo('Asia/Kolkata'))


def fetch_news_rss():
    items = fetch_feeds()
    if not items:
        return 0, 'no_items'

    news_objects = []
    for item in items:
        text = f"{item['title']} {item['summary']}"
        sentiment = score_sentiment(text)
        tags = tag_news(text)
        news_objects.append(
            NewsItem(
                published_at=item['published_at'],
                source=item['source'][:100],
                title=item['title'][:500],
                url=item['url'],
                summary=item['summary'],
                sentiment=sentiment,
                relevance=1.0,
                entities_json=tags,
            )
        )

    NewsItem.objects.bulk_create(news_objects, ignore_conflicts=True)
    return len(news_objects), ''


def fetch_announcements_nse(symbol='JSLL'):
    items = fetch_nse_announcements(symbol=symbol)
    if not items:
        return 0, 'no_items'

    recent_since = timezone.now() - timezone.timedelta(days=7)
    existing = set(
        Announcement.objects.filter(published_at__gte=recent_since)
        .values_list('headline', 'published_at')
    )
    existing_results_days = set(
        Announcement.objects.filter(published_at__gte=recent_since, type='results')
        .values_list('published_at', flat=True)
    )
    existing_results_days = {dt.date() for dt in existing_results_days}

    to_create = []
    for item in items:
        published_at = _ensure_ist(item['published_at'])
        key = (item['headline'], published_at)
        if key in existing:
            continue

        classification = classify_announcement(item['headline'])
        typ = classification['type']
        impact_score = classification['impact_score']
        low_priority = classification['low_priority']

        if typ == 'results' and published_at.date() in existing_results_days:
            low_priority = True

        dedupe_hash = compute_dedupe_hash(item['headline'], published_at, typ)

        to_create.append(
            Announcement(
                published_at=published_at,
                headline=item['headline'][:500],
                url=item['url'],
                type=typ,
                polarity=classification['polarity'],
                impact_score=impact_score,
                low_priority=low_priority,
                dedupe_hash=dedupe_hash,
                tags_json={'tags': classification['tags']},
            )
        )
        if typ == 'results':
            existing_results_days.add(published_at.date())

    Announcement.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create), ''


def create_announcement_from_text(headline, published_at, url=''):
    classification = classify_announcement(headline)
    return Announcement.objects.create(
        published_at=_ensure_ist(published_at),
        headline=headline[:500],
        url=url,
        type=classification['type'],
        polarity=classification['polarity'],
        impact_score=classification['impact_score'],
        low_priority=classification['low_priority'],
        dedupe_hash=compute_dedupe_hash(headline, published_at, classification['type']),
        tags_json={'tags': classification['tags']},
    )