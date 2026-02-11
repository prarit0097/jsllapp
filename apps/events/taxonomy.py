import hashlib


def _normalize(text):
    return ' '.join((text or '').lower().split())


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
        'unaudited',
        'quarter',
        'results',
    )

    if has('outcome of board meeting') and has(*results_keywords):
        typ = 'results'
        impact_score = 60
    elif has(*results_keywords):
        typ = 'results'
        impact_score = 60
    elif has('outcome of board meeting'):
        typ = 'board_meeting'
        impact_score = 10

    if has('dividend'):
        typ = 'dividend'
        polarity = 1
        impact_score = max(impact_score, 40)

    if has('bonus') or has('split'):
        typ = 'bonus' if has('bonus') else 'split'
        polarity = 1
        impact_score = max(impact_score, 45)

    if has('fund raise', 'preferential', 'warrant'):
        typ = 'fundraise'
        impact_score = max(impact_score, 25)

    if has('penalty', 'court', 'notice', 'legal'):
        typ = 'legal'
        polarity = -1
        impact_score = min(impact_score, -40) if impact_score else -40

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


def compute_dedupe_hash(headline, published_at, typ):
    day = published_at.date().isoformat() if published_at else 'unknown'
    base = f"{day}|{typ}|{_normalize(headline)}"
    return hashlib.md5(base.encode('utf-8')).hexdigest()


def tag_news(text):
    text_lower = (text or '').lower()
    tags = {}
    for key in ['results', 'order', 'fraud', 'penalty', 'dividend', 'bonus', 'split']:
        if key in text_lower:
            tags[key] = True
    return tags
