import os
from datetime import datetime
from urllib.parse import quote_plus

import feedparser
from django.utils import timezone


DEFAULT_KEYWORDS = [
    'JSLL',
    'Jeena Sikho Lifecare',
    'Jeena Sikho',
]


def _default_rss_urls():
    urls = []
    for keyword in DEFAULT_KEYWORDS:
        query = quote_plus(keyword)
        urls.append(f"https://news.google.com/rss/search?q={query}")
    return urls


def get_rss_urls():
    override = os.getenv('EVENTS_RSS_URLS', '').strip()
    urls = []
    if override:
        urls.extend([item.strip() for item in override.split(',') if item.strip()])
    urls.extend(_default_rss_urls())
    return list(dict.fromkeys(urls))


def parse_entry(entry, feed_title):
    title = entry.get('title', '').strip()
    link = entry.get('link', '').strip()
    summary = entry.get('summary', '').strip()

    published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    if published_parsed:
        published_at = datetime(*published_parsed[:6], tzinfo=timezone.now().tzinfo)
    else:
        published_at = timezone.now()

    return {
        'title': title,
        'url': link,
        'summary': summary,
        'published_at': published_at,
        'source': feed_title or 'rss',
    }


def fetch_feeds():
    items = []
    for url in get_rss_urls():
        feed = feedparser.parse(url)
        feed_title = getattr(feed.feed, 'title', 'rss')
        for entry in feed.entries:
            items.append(parse_entry(entry, feed_title))
    return items