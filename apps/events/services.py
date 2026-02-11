from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from .models import Announcement, NewsItem
from .nse import fetch_nse_announcements
from .rss import fetch_feeds
from .sentiment import score_sentiment
from .taxonomy import classify_announcement, tag_news
from .utils import build_announcement_dedupe_key


def _ensure_ist(dt):
    if not dt:
        return None
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
        return {
            'parsed_count': 0,
            'saved_count': 0,
            'updated_count': 0,
            'skipped_duplicates': 0,
            'parse_errors': 0,
            'errors': ['no_items'],
        }

    created_count = 0
    updated_count = 0
    skipped_duplicates = 0
    parse_errors = 0
    seen_keys = set()
    error_samples = []

    for idx, item in enumerate(items):
        headline = ' '.join((item.get('headline') or '').split())
        if not headline:
            continue
        published_at = _ensure_ist(item.get('published_at'))
        if not published_at:
            parse_errors += 1
            if len(error_samples) < 3:
                error_samples.append(
                    {
                        'row_index': idx,
                        'headline': headline,
                        'published_text': item.get('published_text', ''),
                        'doc_url': item.get('url', ''),
                        'error': repr(item.get('parse_error')),
                    }
                )
            continue

        dedupe_key = build_announcement_dedupe_key(
            symbol=symbol,
            headline=headline,
            published_at=published_at,
            doc_url=item.get('url', ''),
            source_id=item.get('source_id', ''),
        )
        if not dedupe_key:
            parse_errors += 1
            if len(error_samples) < 3:
                error_samples.append(
                    {
                        'row_index': idx,
                        'headline': headline,
                        'published_text': item.get('published_text', ''),
                        'doc_url': item.get('url', ''),
                        'error': 'dedupe_key_empty',
                    }
                )
            continue
        if dedupe_key in seen_keys:
            skipped_duplicates += 1
            continue
        seen_keys.add(dedupe_key)

        classification = classify_announcement(headline)
        defaults = {
            'published_at': published_at,
            'headline': headline[:500],
            'url': item.get('url', ''),
            'type': classification['type'],
            'polarity': classification['polarity'],
            'impact_score': classification['impact_score'],
            'low_priority': classification['low_priority'],
            'dedupe_hash': None,
            'tags_json': {'tags': classification['tags']},
        }

        try:
            obj, created = Announcement.objects.update_or_create(
                dedupe_key=dedupe_key,
                defaults=defaults,
            )
        except IntegrityError:
            skipped_duplicates += 1
            continue

        if created:
            created_count += 1
        else:
            updated_count += 1

    if error_samples:
        for sample in error_samples:
            print(
                'NSE parse failure sample:',
                f"row={sample['row_index']}",
                f"headline={sample['headline']}",
                f"published_text={sample['published_text']}",
                f"doc_url={sample['doc_url']}",
                f"error={sample['error']}",
            )

    return {
        'parsed_count': len(items),
        'saved_count': created_count,
        'updated_count': updated_count,
        'skipped_duplicates': skipped_duplicates,
        'parse_errors': parse_errors,
        'errors': [],
    }


def create_announcement_from_text(headline, published_at, url=''):
    classification = classify_announcement(headline)
    published_at_ist = _ensure_ist(published_at)
    if not published_at_ist:
        raise ValueError('published_at required')
    symbol = getattr(settings, 'JSLL_TICKER', 'JSLL')
    dedupe_key = build_announcement_dedupe_key(symbol, headline, published_at_ist, url, '')
    return Announcement.objects.create(
        dedupe_key=dedupe_key,
        published_at=published_at_ist,
        headline=headline[:500],
        url=url,
        type=classification['type'],
        polarity=classification['polarity'],
        impact_score=classification['impact_score'],
        low_priority=classification['low_priority'],
        dedupe_hash=None,
        tags_json={'tags': classification['tags']},
    )
