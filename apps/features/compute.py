from datetime import timedelta
from math import sqrt
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone

from apps.events.models import Announcement, NewsItem
from apps.market.models import Ohlc1m


def localtime_floor_minute(ts):
    if ts is None:
        return None
    local = timezone.localtime(ts)
    return local.replace(second=0, microsecond=0)


def _safe_std(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return sqrt(var)


def _rsi_14(closes):
    if len(closes) < 15:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    deltas = deltas[-14:]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / 14 if gains else 0.0
    avg_loss = sum(losses) / 14 if losses else 0.0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_14(candles):
    if len(candles) < 15:
        return 0.0
    trs = []
    for i in range(-14, 0):
        cur = candles[i]
        prev = candles[i - 1]
        high = cur['high']
        low = cur['low']
        prev_close = prev['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def compute_features_for_ts(ts):
    ts_floor = localtime_floor_minute(ts)
    if ts_floor is None:
        return {}

    candles_qs = Ohlc1m.objects.filter(ts__lte=ts_floor).order_by('-ts')[:240]
    candles = list(candles_qs)
    candles.reverse()

    feature_json = {
        'ts': ts_floor.isoformat(),
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
        'news_count_24h': 0,
        'news_sent_avg_24h': 0.0,
        'realized_vol_60m': 0.0,
        'regime_high_vol': 0,
        'regime_label': 'calm',
        'insufficient_history': False,
    }

    if len(candles) < 2:
        feature_json['insufficient_history'] = True
        return feature_json

    closes = [c.close for c in candles]
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles]

    last_close = closes[-1]
    prev_close = closes[-2]

    if prev_close != 0:
        feature_json['ret_1m'] = (last_close / prev_close) - 1.0

    if len(closes) > 5 and closes[-6] != 0:
        feature_json['ret_5m'] = (last_close / closes[-6]) - 1.0

    if len(closes) > 15 and closes[-16] != 0:
        feature_json['ret_15m'] = (last_close / closes[-16]) - 1.0

    feature_json['rsi_14'] = _rsi_14(closes[-15:])

    candle_rows = [
        {
            'high': highs[i],
            'low': lows[i],
            'close': closes[i],
        }
        for i in range(len(closes))
    ]
    feature_json['atr_14'] = _atr_14(candle_rows)

    if opens[-1] != 0:
        feature_json['candle_body_pct'] = abs(last_close - opens[-1]) / opens[-1] * 100.0
        feature_json['range_pct'] = abs(highs[-1] - lows[-1]) / opens[-1] * 100.0

    if len(vols) >= 20:
        last_20 = vols[-20:]
        mean_20 = sum(last_20) / len(last_20)
        std_20 = _safe_std(last_20)
        feature_json['vol_z_20'] = 0.0 if std_20 == 0 else (vols[-1] - mean_20) / std_20

    if len(vols) >= 60:
        last_60 = vols[-60:]
        mean_60 = sum(last_60) / len(last_60)
        std_60 = _safe_std(last_60)
        feature_json['vol_z_60'] = 0.0 if std_60 == 0 else (vols[-1] - mean_60) / std_60

    returns_1m = []
    for i in range(1, len(closes)):
        if closes[i - 1] != 0:
            returns_1m.append((closes[i] / closes[i - 1]) - 1.0)
    if len(returns_1m) >= 60:
        returns_1m = returns_1m[-60:]
    if returns_1m:
        feature_json['realized_vol_60m'] = _safe_std(returns_1m)

    now_ist = ts_floor.astimezone(ZoneInfo('Asia/Kolkata'))
    ann_24h_since = now_ist - timedelta(hours=24)
    ann_7d_since = now_ist - timedelta(days=7)

    ann_qs = Announcement.objects.filter(published_at__lte=ts_floor, low_priority=False)
    ann_24h = ann_qs.filter(published_at__gte=ann_24h_since)
    ann_7d = ann_qs.filter(published_at__gte=ann_7d_since)

    feature_json['ann_high_count_24h'] = ann_24h.filter(impact_score__gte=10).count()
    feature_json['ann_impact_sum_24h'] = ann_24h.aggregate(total_sum=models.Sum('impact_score')).get('total_sum') or 0
    feature_json['ann_impact_sum_7d'] = ann_7d.aggregate(total_sum=models.Sum('impact_score')).get('total_sum') or 0

    results_flag = ann_7d.filter(type__in=['results', 'board_meeting'], headline__icontains='result').exists()
    results_flag = results_flag or ann_7d.filter(type__in=['results', 'board_meeting'], headline__icontains='financial').exists()
    feature_json['ann_results_flag_7d'] = 1 if results_flag else 0

    latest_high = ann_qs.filter(impact_score__gte=10).order_by('-published_at').first()
    if latest_high:
        delta = ts_floor - latest_high.published_at
        feature_json['time_since_last_high_impact_min'] = int(delta.total_seconds() / 60)

    news_24h_since = now_ist - timedelta(hours=24)
    news_qs = NewsItem.objects.filter(published_at__lte=ts_floor, published_at__gte=news_24h_since)
    feature_json['news_count_24h'] = news_qs.count()
    feature_json['news_sent_avg_24h'] = news_qs.aggregate(avg_sent=models.Avg('sentiment')).get('avg_sent') or 0.0

    vol = feature_json['realized_vol_60m']
    if vol >= 0.005:
        feature_json['regime_label'] = 'volatile'
        feature_json['regime_high_vol'] = 1
    elif vol >= 0.002:
        feature_json['regime_label'] = 'active'
    else:
        feature_json['regime_label'] = 'calm'

    return feature_json
