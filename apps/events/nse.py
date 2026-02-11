import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


def _headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/',
        'Connection': 'keep-alive',
    }


def _normalize_published_text(text):
    if not text:
        return ''
    cleaned = ' '.join(str(text).strip().replace('IST', '').split())
    return cleaned


def parse_nse_datetime_to_utc(published_text):
    text = _normalize_published_text(published_text)
    if not text:
        raise ValueError('empty published_text')

    formats = [
        '%d-%b-%Y %H:%M:%S',
        '%d-%b-%Y %H:%M',
        '%d/%m/%Y, %I:%M:%S %p',
        '%d/%m/%Y %I:%M:%S %p',
        '%d/%m/%Y, %I:%M %p',
        '%d/%m/%Y %I:%M %p',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            ist = dt.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
            return ist.astimezone(ZoneInfo('UTC'))
        except ValueError:
            continue

    raise ValueError(f'unrecognized published_text format: {text}')


def _normalize_url(url):
    if not url:
        return ''
    url = url.strip()
    if url.startswith('/'):
        return f'https://www.nseindia.com{url}'
    return url


def _source_id_from_url(url, fallback=''):
    if not url:
        return fallback
    parts = url.split('/')
    return parts[-1] if parts else fallback


def _fetch_json_announcements(session, symbol):
    url = f'https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}'
    resp = session.get(url, headers=_headers(), timeout=10)
    if resp.status_code != 200:
        return []
    data = resp.json()
    items = []
    for row in data:
        headline = (row.get('desc') or '').strip()
        broadcast = row.get('dt', '')
        doc_url = row.get('attchmntFile', '')
        items.append(
            {
                'headline': headline,
                'published_text': broadcast,
                'url': _normalize_url(doc_url),
                'source_id': row.get('annId', '') or _source_id_from_url(doc_url, broadcast),
                'raw': row,
            }
        )
    return items


def _fetch_html_announcements(session, symbol):
    url = f'https://www.nseindia.com/get-quote/equity?symbol={symbol}'
    resp = session.get(url, headers=_headers(), timeout=10)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    items = []
    for card in soup.select('.announcementList li'):
        headline = card.get_text(strip=True)
        items.append({'headline': headline, 'published_text': '', 'url': '', 'source_id': '', 'raw': {}})
    return items


def fetch_nse_announcements(symbol='JSLL'):
    session = requests.Session()
    session.get('https://www.nseindia.com/', headers=_headers(), timeout=10)
    time.sleep(0.5)

    items = _fetch_json_announcements(session, symbol)
    if not items:
        items = _fetch_html_announcements(session, symbol)

    results = []
    for item in items:
        published_text = item.get('published_text')
        try:
            published_at = parse_nse_datetime_to_utc(published_text)
            parse_error = None
        except Exception as exc:
            published_at = None
            parse_error = exc

        results.append(
            {
                'headline': (item.get('headline') or '').strip(),
                'published_at': published_at,
                'published_text': published_text,
                'url': (item.get('url') or '').strip(),
                'source_id': item.get('source_id', ''),
                'parse_error': parse_error,
                'raw': item.get('raw', {}),
            }
        )

    results = [r for r in results if r['headline']]
    results.sort(key=lambda r: r['published_at'] or datetime.min, reverse=True)
    return results
