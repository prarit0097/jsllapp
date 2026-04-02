
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
                    'vwap_dist': feature_json.get('vwap_dist', 0.0),
                },
                'top_reasons': [
                    'Insufficient candle history',
                    'Scores held at neutral baseline',
                ],
                'category_reasons': {
                    'price_action': 'Insufficient history',
                    'volume': 'Insufficient history',
                    'announcements': 'Insufficient history',
                    'news': 'Insufficient history',
                    'regime': 'Insufficient history',
                },
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
    vwap_dist = feature_json.get('vwap_dist', 0.0)

    # ── Price action ──
    price_action = 50 + ret_15m * 2000
    if 40 <= rsi_14 <= 60:
        price_action += 8
    elif rsi_14 >= 70 or rsi_14 <= 30:
        price_action -= 12

    if rsi_14 >= 70:
        pa_reason = f'RSI overbought ({rsi_14:.0f}); 15m return {ret_15m*100:.2f}%'
    elif rsi_14 <= 30:
        pa_reason = f'RSI oversold ({rsi_14:.0f}); 15m return {ret_15m*100:.2f}%'
    elif ret_15m >= 0.005:
        pa_reason = f'Positive 15m momentum ({ret_15m*100:.2f}%)'
    elif ret_15m <= -0.005:
        pa_reason = f'Negative 15m momentum ({ret_15m*100:.2f}%)'
    else:
        pa_reason = f'Neutral momentum; RSI {rsi_14:.0f}'

    # ── Volume ──
    vol_z_capped = max(-3.0, min(3.0, vol_z_20))
    volume = 50 + vol_z_capped * 15

    if vol_z_20 >= 2.0:
        vol_reason = f'Strong volume surge (z={vol_z_20:.1f})'
    elif vol_z_20 >= 1.0:
        vol_reason = f'Above-average volume (z={vol_z_20:.1f})'
    elif vol_z_20 <= -1.5:
        vol_reason = f'Low volume (z={vol_z_20:.1f})'
    else:
        vol_reason = f'Normal volume (z={vol_z_20:.1f})'

    # ── News ──
    news = 50
    if news_count_24h > 0:
        news += news_sent_avg_24h * 30
        news += min(news_count_24h, 5) * 2

    if news_count_24h == 0:
        news_reason = 'No news in last 24h'
    elif news_sent_avg_24h >= 0.2:
        news_reason = f'Positive news sentiment ({news_count_24h} items, avg {news_sent_avg_24h:.2f})'
    elif news_sent_avg_24h <= -0.2:
        news_reason = f'Negative news sentiment ({news_count_24h} items, avg {news_sent_avg_24h:.2f})'
    else:
        news_reason = f'{news_count_24h} news items; neutral sentiment'

    # ── Announcements ──
    announcements = 50 + ann_impact_sum_24h * 0.4
    if results_flag_7d:
        announcements += 10

    if ann_impact_sum_24h >= 20:
        ann_reason = f'High-impact announcements in 24h (sum={ann_impact_sum_24h})'
    elif results_flag_7d:
        ann_reason = 'Results/board meeting announced in last 7 days'
    elif ann_impact_sum_24h > 0:
        ann_reason = f'Some announcement activity (impact sum {ann_impact_sum_24h})'
    else:
        ann_reason = 'No significant announcements'

    # ── Regime ──
    if regime_label == 'volatile':
        regime = 35
        reg_reason = f'Volatile regime (vol={realized_vol_60m:.4f})'
    elif regime_label == 'active':
        regime = 50
        reg_reason = f'Active regime (vol={realized_vol_60m:.4f})'
    else:
        regime = 65
        reg_reason = f'Calm regime (vol={realized_vol_60m:.4f})'

    # Add VWAP signal to regime context when meaningful
    if abs(vwap_dist) >= 0.005:
        direction = 'above' if vwap_dist > 0 else 'below'
        reg_reason += f'; {abs(vwap_dist)*100:.2f}% {direction} VWAP'

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

    # Aggregate top reasons for the overview card
    top_reasons = []
    if ann_impact_sum_24h >= 20:
        top_reasons.append('High announcement impact in last 24h')
    if vol_z_20 >= 1.5:
        top_reasons.append('Volume surge vs 20m average')
    if ret_15m >= 0.005:
        top_reasons.append('Positive 15m momentum')
    if ret_15m <= -0.005:
        top_reasons.append('Negative 15m momentum')
    if rsi_14 >= 70:
        top_reasons.append('RSI elevated (overbought)')
    if rsi_14 <= 30:
        top_reasons.append('RSI depressed (oversold)')
    if news_count_24h > 0 and news_sent_avg_24h >= 0.2:
        top_reasons.append('Positive news sentiment')
    if news_count_24h > 0 and news_sent_avg_24h <= -0.2:
        top_reasons.append('Negative news sentiment')
    if abs(vwap_dist) >= 0.005:
        direction = 'above' if vwap_dist > 0 else 'below'
        top_reasons.append(f'Price {abs(vwap_dist)*100:.1f}% {direction} VWAP')

    if not top_reasons:
        top_reasons.append('Mixed signals; neutral stance')

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
                'vwap_dist': vwap_dist,
            },
            'top_reasons': top_reasons[:3],
            'category_reasons': {
                'price_action': pa_reason,
                'volume': vol_reason,
                'announcements': ann_reason,
                'news': news_reason,
                'regime': reg_reason,
            },
        },
    }
