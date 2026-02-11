import hashlib
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


def _normalize(text):
    return ' '.join((text or '').lower().split())


def _normalize_url(url):
    if not url:
        return ''
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path
        return _normalize(urlunsplit((scheme, netloc, path, '', '')))
    except Exception:
        return _normalize(url)


def _floor_to_minute_ist(dt):
    if not dt:
        return None
    try:
        local = dt.astimezone(ZoneInfo('Asia/Kolkata'))
    except Exception:
        local = dt
    return local.replace(second=0, microsecond=0)


def classify_announcement(headline, summary=''):
    text = f"{headline} {summary}".lower()
    tags = []
    low_priority = False
    typ = 'other'
    polarity = 0
    impact_score = 0

    def has(*keywords):
        return any(keyword in text for keyword in keywords)

    results_keywords = (
        'financial results',
        'unaudited financial results',
        'unaudited',
        'limited review',
        'standalone',
        'consolidated',
        'quarter',
        'nine months',
    )

    if has('outcome of board meeting') and has(*results_keywords):
        typ = 'results'
        impact_score = 70
        low_priority = False
    elif has('financial results', 'unaudited financial results', 'unaudited'):
        typ = 'results'
        impact_score = 70
        low_priority = False
    elif has('outcome of board meeting'):
        typ = 'board_meeting'
        impact_score = 25
        low_priority = False

    if has('dividend'):
        typ = 'dividend'
        polarity = 1
        impact_score = max(impact_score, 40)
        low_priority = False

    if has('bonus') or has('split'):
        typ = 'bonus' if has('bonus') else 'split'
        polarity = 1
        impact_score = max(impact_score, 45)
        low_priority = False

    if has('fund raise', 'preferential', 'warrant'):
        typ = 'fundraise'
        impact_score = max(impact_score, 25)
        low_priority = False

    if has('penalty', 'court', 'notice', 'legal'):
        typ = 'legal'
        polarity = -1
        impact_score = min(impact_score, -40) if impact_score else -40
        low_priority = False

    if has('insider trading', 'insider'):
        typ = 'insider'
        low_priority = True
        impact_score = 5

    if has('copy of newspaper publication', 'xbrl', 'compliance', 'submission of copies'):
        typ = 'compliance'
        low_priority = True
        impact_score = 0

    if typ == 'other':
        low_priority = True
        impact_score = 0

    if impact_score >= 50:
        tags.append('high_impact')
    if low_priority:
        tags.append('low_priority')

    impact_score = max(-100, min(100, impact_score))

    return {
        'type': typ,
        'polarity': polarity,
        'impact_score': impact_score,
        'low_priority': low_priority,
        'tags': tags,
    }


def compute_soft_key(published_at, url='', symbol=''):
    normalized_url = _normalize_url(url)
    if not normalized_url:
        return None
    dt_floor = _floor_to_minute_ist(published_at)
    dt_key = dt_floor.isoformat() if dt_floor else 'unknown'
    return f"{symbol}|{dt_key}|{normalized_url}"


def compute_dedupe_hash(headline, published_at, url='', symbol=''):
    dt_floor = _floor_to_minute_ist(published_at)
    dt_key = dt_floor.isoformat() if dt_floor else 'unknown'
    normalized_url = _normalize_url(url)
    if normalized_url:
        base = f"{symbol}|{dt_key}|{_normalize(headline)}|{normalized_url}"
    else:
        base = f"{symbol}|{dt_key}|{_normalize(headline)}"
    return hashlib.md5(base.encode('utf-8')).hexdigest()


def tag_news(text):
    text_lower = (text or '').lower()
    tags = {}
    for key in ['results', 'order', 'fraud', 'penalty', 'dividend', 'bonus', 'split']:
        if key in text_lower:
            tags[key] = True
    return tags
