from zoneinfo import ZoneInfo

from django.conf import settings
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


def _load_existing_hashes(since, symbol):
    existing_hashes = set()
    qs = Announcement.objects.filter(published_at__gte=since).only('headline', 'published_at', 'url')
    for ann in qs.iterator():
        existing_hashes.add(compute_dedupe_hash(ann.headline, ann.published_at, ann.url, symbol))
    return existing_hashes


def fetch_announcements_nse(symbol='JSLL'):
    items = fetch_nse_announcements(symbol=symbol)
    if not items:
        return {
            'parsed_count': 0,
            'saved_count': 0,
            'skipped_duplicates': 0,
            'errors': ['no_items'],
        }

    recent_since = timezone.now() - timezone.timedelta(days=14)
    existing_hashes = _load_existing_hashes(recent_since, symbol)

    to_create = []
    skipped_duplicates = 0
    seen_hashes = set()
    for item in items:
        headline = ' '.join((item['headline'] or '').split())
        if not headline:
            continue
        published_at = _ensure_ist(item['published_at'])
        dedupe_hash = compute_dedupe_hash(headline, published_at, item.get('url', ''), symbol)
        if dedupe_hash in existing_hashes or dedupe_hash in seen_hashes:
            skipped_duplicates += 1
            continue

        classification = classify_announcement(headline)

        to_create.append(
            Announcement(
                published_at=published_at,
                headline=headline[:500],
                url=item['url'],
                type=classification['type'],
                polarity=classification['polarity'],
                impact_score=classification['impact_score'],
                low_priority=classification['low_priority'],
                dedupe_hash=dedupe_hash,
                tags_json={'tags': classification['tags']},
            )
        )
        existing_hashes.add(dedupe_hash)
        seen_hashes.add(dedupe_hash)

    Announcement.objects.bulk_create(to_create, ignore_conflicts=True)
    return {
        'parsed_count': len(items),
        'saved_count': len(to_create),
        'skipped_duplicates': skipped_duplicates,
        'errors': [],
    }


def create_announcement_from_text(headline, published_at, url=''):
    classification = classify_announcement(headline)
    published_at_ist = _ensure_ist(published_at)
    symbol = getattr(settings, 'JSLL_TICKER', 'JSLL')
    return Announcement.objects.create(
        published_at=published_at_ist,
        headline=headline[:500],
        url=url,
        type=classification['type'],
        polarity=classification['polarity'],
        impact_score=classification['impact_score'],
        low_priority=classification['low_priority'],
        dedupe_hash=compute_dedupe_hash(headline, published_at_ist, url, symbol),
        tags_json={'tags': classification['tags']},
    )
