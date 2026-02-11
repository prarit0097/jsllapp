import re


def classify_announcement(text):
    text_lower = (text or '').lower()
    tags = {}
    typ = 'other'
    polarity = 0
    impact_score = 0

    def has(*keywords):
        return any(keyword in text_lower for keyword in keywords)

    if has('financial results', 'unaudited'):
        typ = 'results'
        impact_score = 50
    if has('outcome of board meeting') and has('result', 'results', 'financial results', 'unaudited'):
        typ = 'results'
        impact_score = max(impact_score, 50)
    if has('result', 'results') and typ != 'results':
        typ = 'results'
        impact_score = max(impact_score, 30)
    if has('board meeting') and typ != 'results':
        typ = 'board_meeting'
        impact_score = max(impact_score, 10)
    if has('dividend'):
        typ = 'dividend'
        polarity = 1
        impact_score = max(impact_score, 25)
    if has('bonus'):
        typ = 'bonus'
        polarity = 1
        impact_score = max(impact_score, 40)
    if has('split'):
        typ = 'split'
        polarity = 1
        impact_score = max(impact_score, 35)
    if has('fund raise', 'preferential', 'warrant'):
        typ = 'fundraise'
        impact_score = max(impact_score, 20)
    if has('order', 'contract'):
        typ = 'order'
        polarity = 1
        impact_score = max(impact_score, 30)
    if has('penalty', 'notice', 'court', 'legal', 'fraud'):
        typ = 'legal'
        polarity = -1
        impact_score = min(impact_score, -40) if impact_score else -40
    if has('insider trading'):
        typ = 'insider'
        impact_score = 5
    if has('copy of newspaper publication'):
        typ = 'compliance'
        impact_score = 0

    if has('approved', 'wins', 'record'):
        impact_score += 10
        tags['positive_signal'] = True
    if has('fraud', 'penalty', 'loss'):
        impact_score -= 20
        tags['negative_signal'] = True

    if typ in {'dividend', 'bonus', 'order'}:
        polarity = 1
    if typ in {'legal'}:
        polarity = -1

    if typ in {'compliance', 'insider'} and impact_score < 10:
        tags['low_priority'] = True

    impact_score = max(-100, min(100, impact_score))
    tags['type'] = typ

    return typ, polarity, impact_score, tags


def tag_news(text):
    text_lower = (text or '').lower()
    tags = {}
    for key in ['results', 'order', 'fraud', 'penalty', 'dividend', 'bonus', 'split']:
        if key in text_lower:
            tags[key] = True
    return tags