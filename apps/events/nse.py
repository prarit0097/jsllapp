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


def _parse_broadcast_dt(text):
    if not text:
        return None
    text = text.strip()
    formats = [
        '%d-%b-%Y %H:%M:%S',
        '%d-%b-%Y %H:%M',
        '%d %b %Y %H:%M:%S',
        '%d %b %Y %H:%M',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
        except ValueError:
            continue
    return None


def _fetch_json_announcements(session, symbol):
    url = f'https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}'
    resp = session.get(url, headers=_headers(), timeout=10)
    if resp.status_code != 200:
        return []
    data = resp.json()
    items = []
    for row in data:
        headline = row.get('desc', '').strip()
        broadcast = row.get('dt', '')
        url = row.get('attchmntFile', '')
        items.append(
            {
                'headline': headline,
                'broadcast': broadcast,
                'url': url,
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
        items.append({'headline': headline, 'broadcast': '', 'url': ''})
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
        broadcast_dt = _parse_broadcast_dt(item.get('broadcast'))
        results.append(
            {
                'headline': item.get('headline', '').strip(),
                'published_at': broadcast_dt,
                'url': item.get('url', '').strip(),
            }
        )

    results = [r for r in results if r['headline']]
    results.sort(key=lambda r: r['published_at'] or datetime.min, reverse=True)
    return results