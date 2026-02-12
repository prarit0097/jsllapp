from django.utils import timezone


def localtime_floor_minute(ts):
    if ts is None:
        return None
    local = timezone.localtime(ts)
    return local.replace(second=0, microsecond=0)


def compute_features_for_ts(ts):
    if ts is None:
        return {}
    return {
        'ts': ts.isoformat(),
        'ret_1m': 0.0,
        'ret_5m': 0.0,
        'ret_15m': 0.0,
        'rsi_14': 50.0,
        'atr_14': 0.0,
        'candle_body_pct': 0.0,
        'range_pct': 0.0,
        'vol_z_20': 0.0,
        'vol_z_60': 0.0,
        'vwap_dist': 0.0,
        'ann_high_count_24h': 0,
        'ann_impact_sum_24h': 0,
        'ann_impact_sum_7d': 0,
        'ann_results_flag_7d': 0,
        'time_since_last_high_impact_min': None,
        'news_count_2h': 0,
        'news_sent_avg_2h': 0.0,
        'realized_vol_60m': 0.0,
        'regime_high_vol': 0,
    }
