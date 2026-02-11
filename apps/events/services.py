from django.utils import timezone

from .models import Announcement, NewsItem
from .nse import fetch_nse_announcements
from .rss import fetch_feeds
from .sentiment import score_sentiment
from .taxonomy import classify_announcement, tag_news


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

    existing = set(
        Announcement.objects.filter(published_at__gte=timezone.now() - timezone.timedelta(days=7))
        .values_list('headline', 'published_at')
    )

    to_create = []
    for item in items:
        published_at = item['published_at'] or timezone.now()
        key = (item['headline'], published_at)
        if key in existing:
            continue
        typ, polarity, impact_score, tags = classify_announcement(item['headline'])
        to_create.append(
            Announcement(
                published_at=published_at,
                headline=item['headline'][:500],
                url=item['url'],
                type=typ,
                polarity=polarity,
                impact_score=impact_score,
                tags_json=tags,
            )
        )

    Announcement.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create), ''


def create_announcement_from_text(headline, published_at, url=''):
    typ, polarity, impact_score, tags = classify_announcement(headline)
    return Announcement.objects.create(
        published_at=published_at,
        headline=headline[:500],
        url=url,
        type=typ,
        polarity=polarity,
        impact_score=impact_score,
        tags_json=tags,
    )