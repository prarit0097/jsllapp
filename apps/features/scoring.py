
def _clamp(score):
    return max(0, min(100, int(score)))


def score_from_features(feature_json):
    price_action = 50
    volume = 50
    news = 50
    announcements = 50
    regime = 50

    overall = _clamp(
        price_action * 0.35
        + volume * 0.15
        + news * 0.20
        + announcements * 0.20
        + regime * 0.10
    )

    return {
        'price_action_score': _clamp(price_action),
        'volume_score': _clamp(volume),
        'news_score': _clamp(news),
        'announcements_score': _clamp(announcements),
        'regime_score': _clamp(regime),
        'overall_score': overall,
        'explain_json': {
            'key_features': {
                'ret_15m': feature_json.get('ret_15m', 0.0),
                'rsi_14': feature_json.get('rsi_14', 50.0),
                'vol_z_20': feature_json.get('vol_z_20', 0.0),
                'ann_impact_sum_24h': feature_json.get('ann_impact_sum_24h', 0),
                'results_flag_7d': feature_json.get('ann_results_flag_7d', 0),
                'realized_vol_60m': feature_json.get('realized_vol_60m', 0.0),
            },
            'top_reasons': [
                'Baseline scoring (placeholder)',
                'Waiting for richer features',
                'Scores update each minute',
            ],
        },
    }
