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


def _load_existing_hashes(since):
    existing_hashes = set()
    qs = Announcement.objects.filter(published_at__gte=since).only('headline', 'published_at', 'url', 'dedupe_hash')
    for ann in qs.iterator():
        dedupe_hash = ann.dedupe_hash or compute_dedupe_hash(ann.headline, ann.published_at, ann.url)
        existing_hashes.add(dedupe_hash)
    return existing_hashes


def fetch_announcements_nse(symbol='JSLL'):
    items = fetch_nse_announcements(symbol=symbol)
    if not items:
        return 0, 'no_items'

    recent_since = timezone.now() - timezone.timedelta(days=14)
    existing_hashes = _load_existing_hashes(recent_since)

    to_create = []
    for item in items:
        headline = ' '.join((item['headline'] or '').split())
        if not headline:
            continue
        published_at = _ensure_ist(item['published_at'])
        dedupe_hash = compute_dedupe_hash(headline, published_at, item.get('url', ''))
        if dedupe_hash in existing_hashes:
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

    Announcement.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create), ''


def create_announcement_from_text(headline, published_at, url=''):
    classification = classify_announcement(headline)
    published_at_ist = _ensure_ist(published_at)
    return Announcement.objects.create(
        published_at=published_at_ist,
        headline=headline[:500],
        url=url,
        type=classification['type'],
        polarity=classification['polarity'],
        impact_score=classification['impact_score'],
        low_priority=classification['low_priority'],
        dedupe_hash=compute_dedupe_hash(headline, published_at_ist, url),
        tags_json={'tags': classification['tags']},
    )
