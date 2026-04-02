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
    """RSI using Wilder's EMA smoothing (alpha = 1/14).

    Requires at least 29 values to give the EMA enough warm-up time.
    Falls back to neutral 50 if there is insufficient history.
    """
    if len(closes) < 15:
        return 50.0

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    # Seed with simple average of the first 14 changes
    gains_seed = [d for d in deltas[:14] if d > 0]
    losses_seed = [-d for d in deltas[:14] if d < 0]
    avg_gain = sum(gains_seed) / 14
    avg_loss = sum(losses_seed) / 14

    # Apply Wilder's EMA for all subsequent changes
    for d in deltas[14:]:
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * 13 + gain) / 14
        avg_loss = (avg_loss * 13 + loss) / 14

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
        tr = max(
            cur['high'] - cur['low'],
            abs(cur['high'] - prev['close']),
            abs(cur['low'] - prev['close']),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def _compute_vwap(candles, session_date, ist_tz):
    """Compute session VWAP using candles from the current IST trading day."""
    session_candles = [
        c for c in candles
        if c.ts.astimezone(ist_tz).date() == session_date
        and c.volume > 0
    ]
    if not session_candles:
        return None

    total_tp_vol = sum((c.high + c.low + c.close) / 3.0 * c.volume for c in session_candles)
    total_vol = sum(c.volume for c in session_candles)
    return total_tp_vol / total_vol if total_vol > 0 else None


def compute_features_for_ts(ts):
    ts_floor = localtime_floor_minute(ts)
    if ts_floor is None:
        return {}

    # Fetch more candles so Wilder RSI EMA has adequate warm-up (≥ 43 = 3x period + 1)
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
        'atr_pct': 0.0,
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

    # Use full close history for Wilder EMA warm-up
    feature_json['rsi_14'] = _rsi_14(closes)

    candle_rows = [{'high': highs[i], 'low': lows[i], 'close': closes[i]} for i in range(len(closes))]
    atr = _atr_14(candle_rows)
    feature_json['atr_14'] = atr
    feature_json['atr_pct'] = (atr / last_close * 100.0) if last_close != 0 else 0.0

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

    # ── VWAP distance (session-scoped) ──
    ist_tz = ZoneInfo('Asia/Kolkata')
    session_date = ts_floor.astimezone(ist_tz).date()
    vwap = _compute_vwap(candles, session_date, ist_tz)
    if vwap and last_close != 0:
        feature_json['vwap_dist'] = (last_close - vwap) / last_close

    # ── Event features ──
    now_ist = ts_floor.astimezone(ist_tz)
    ann_24h_since = now_ist - timedelta(hours=24)
    ann_7d_since = now_ist - timedelta(days=7)

    ann_qs = Announcement.objects.filter(published_at__lte=ts_floor, low_priority=False)
    ann_24h = ann_qs.filter(published_at__gte=ann_24h_since)
    ann_7d = ann_qs.filter(published_at__gte=ann_7d_since)

    feature_json['ann_high_count_24h'] = ann_24h.filter(impact_score__gte=10).count()
    feature_json['ann_impact_sum_24h'] = ann_24h.aggregate(
        total_sum=models.Sum('impact_score')
    ).get('total_sum') or 0
    feature_json['ann_impact_sum_7d'] = ann_7d.aggregate(
        total_sum=models.Sum('impact_score')
    ).get('total_sum') or 0

    results_flag = ann_7d.filter(
        type__in=['results', 'board_meeting'],
        headline__icontains='result',
    ).exists()
    results_flag = results_flag or ann_7d.filter(
        type__in=['results', 'board_meeting'],
        headline__icontains='financial',
    ).exists()
    feature_json['ann_results_flag_7d'] = 1 if results_flag else 0

    latest_high = ann_qs.filter(impact_score__gte=10).order_by('-published_at').first()
    if latest_high:
        delta = ts_floor - latest_high.published_at
        feature_json['time_since_last_high_impact_min'] = int(delta.total_seconds() / 60)

    news_24h_since = now_ist - timedelta(hours=24)
    news_qs = NewsItem.objects.filter(published_at__lte=ts_floor, published_at__gte=news_24h_since)
    feature_json['news_count_24h'] = news_qs.count()
    feature_json['news_sent_avg_24h'] = (
        news_qs.aggregate(avg_sent=models.Avg('sentiment')).get('avg_sent') or 0.0
    )

    # ── Volatility regime ──
    vol = feature_json['realized_vol_60m']
    if vol >= 0.005:
        feature_json['regime_label'] = 'volatile'
        feature_json['regime_high_vol'] = 1
    elif vol >= 0.002:
        feature_json['regime_label'] = 'active'
    else:
        feature_json['regime_label'] = 'calm'

    return feature_json
