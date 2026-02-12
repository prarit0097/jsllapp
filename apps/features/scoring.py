
def _clamp(score):
    return max(0, min(100, int(round(score))))


def score_from_features(feature_json):
    if feature_json.get('insufficient_history'):
        return {
            'price_action_score': 50,
            'volume_score': 50,
            'news_score': 50,
            'announcements_score': 50,
            'regime_score': 50,
            'overall_score': 50,
            'explain_json': {
                'key_features': {
                    'ret_1m': feature_json.get('ret_1m', 0.0),
                    'ret_15m': feature_json.get('ret_15m', 0.0),
                    'rsi_14': feature_json.get('rsi_14', 50.0),
                    'vol_z_20': feature_json.get('vol_z_20', 0.0),
                    'ann_impact_sum_24h': feature_json.get('ann_impact_sum_24h', 0),
                    'results_flag_7d': feature_json.get('ann_results_flag_7d', 0),
                    'realized_vol_60m': feature_json.get('realized_vol_60m', 0.0),
                },
                'top_reasons': [
                    'Insufficient candle history',
                    'Scores held at neutral baseline',
                ],
            },
        }

    ret_15m = feature_json.get('ret_15m', 0.0)
    rsi_14 = feature_json.get('rsi_14', 50.0)
    vol_z_20 = feature_json.get('vol_z_20', 0.0)
    ann_impact_sum_24h = feature_json.get('ann_impact_sum_24h', 0)
    results_flag_7d = feature_json.get('ann_results_flag_7d', 0)
    realized_vol_60m = feature_json.get('realized_vol_60m', 0.0)
    news_count_24h = feature_json.get('news_count_24h', 0)
    news_sent_avg_24h = feature_json.get('news_sent_avg_24h', 0.0)
    regime_label = feature_json.get('regime_label', 'calm')

    price_action = 50 + ret_15m * 2000
    if 40 <= rsi_14 <= 60:
        price_action += 8
    elif rsi_14 >= 70 or rsi_14 <= 30:
        price_action -= 12

    vol_z_capped = max(-3.0, min(3.0, vol_z_20))
    volume = 50 + vol_z_capped * 15

    news = 50
    if news_count_24h > 0:
        news += news_sent_avg_24h * 30
        news += min(news_count_24h, 5) * 2

    announcements = 50 + ann_impact_sum_24h * 0.4
    if results_flag_7d:
        announcements += 10

    if regime_label == 'volatile':
        regime = 35
    elif regime_label == 'active':
        regime = 50
    else:
        regime = 65

    price_action = _clamp(price_action)
    volume = _clamp(volume)
    news = _clamp(news)
    announcements = _clamp(announcements)
    regime = _clamp(regime)

    overall = _clamp(
        price_action * 0.30
        + volume * 0.20
        + announcements * 0.20
        + news * 0.15
        + regime * 0.15
    )

    reasons = []
    if ann_impact_sum_24h >= 20:
        reasons.append('High announcement impact in last 24h')
    if vol_z_20 >= 1.5:
        reasons.append('Volume surge vs 20m average')
    if ret_15m >= 0.005:
        reasons.append('Positive 15m momentum')
    if ret_15m <= -0.005:
        reasons.append('Negative 15m momentum')
    if rsi_14 >= 70:
        reasons.append('RSI elevated (overbought)')
    if rsi_14 <= 30:
        reasons.append('RSI depressed (oversold)')
    if news_count_24h > 0 and news_sent_avg_24h >= 0.2:
        reasons.append('Positive news sentiment')
    if news_count_24h > 0 and news_sent_avg_24h <= -0.2:
        reasons.append('Negative news sentiment')

    if not reasons:
        reasons.append('Mixed signals; neutral stance')

    return {
        'price_action_score': price_action,
        'volume_score': volume,
        'news_score': news,
        'announcements_score': announcements,
        'regime_score': regime,
        'overall_score': overall,
        'explain_json': {
            'key_features': {
                'ret_1m': feature_json.get('ret_1m', 0.0),
                'ret_15m': ret_15m,
                'rsi_14': rsi_14,
                'vol_z_20': vol_z_20,
                'ann_impact_sum_24h': ann_impact_sum_24h,
                'results_flag_7d': results_flag_7d,
                'realized_vol_60m': realized_vol_60m,
            },
            'top_reasons': reasons[:3],
        },
    }
