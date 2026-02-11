POSITIVE_WORDS = {
    'gain', 'gains', 'surge', 'profit', 'profits', 'beat', 'record', 'approved', 'wins',
    'order', 'contract', 'dividend', 'bonus', 'buyback', 'upgrade', 'growth', 'strong',
}

NEGATIVE_WORDS = {
    'loss', 'losses', 'fraud', 'penalty', 'notice', 'lawsuit', 'court', 'decline',
    'downgrade', 'weak', 'fall', 'ban', 'suspension', 'probe',
}


def score_sentiment(text):
    if not text:
        return 0.0
    tokens = [token.strip(".,:;!?()[]{}\"'”).-" ).lower() for token in text.split()]
    pos = sum(1 for token in tokens if token in POSITIVE_WORDS)
    neg = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    if pos == 0 and neg == 0:
        return 0.0
    score = (pos - neg) / max(pos + neg, 1)
    return max(-1.0, min(1.0, score))