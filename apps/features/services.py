from django.db import transaction

from apps.market.models import Ohlc1m

from .compute import compute_features_for_ts, localtime_floor_minute
from .models import Feature1m, SignalScore
from .scoring import score_from_features


def compute_and_store(ts):
    if ts is None:
        return None

    ts_floor = localtime_floor_minute(ts)
    if ts_floor is None:
        return None

    feature_json = compute_features_for_ts(ts_floor)
    scores = score_from_features(feature_json)

    with transaction.atomic():
        Feature1m.objects.update_or_create(
            ts=ts_floor,
            defaults={'feature_json': feature_json},
        )
        score_obj, _created = SignalScore.objects.update_or_create(
            ts=ts_floor,
            defaults={
                'price_action_score': scores['price_action_score'],
                'volume_score': scores['volume_score'],
                'news_score': scores['news_score'],
                'announcements_score': scores['announcements_score'],
                'regime_score': scores['regime_score'],
                'overall_score': scores['overall_score'],
                'explain_json': scores['explain_json'],
            },
        )

    return score_obj


def compute_latest_missing():
    latest_candle = Ohlc1m.objects.order_by('-ts').first()
    if latest_candle is None:
        return None
    return compute_and_store(latest_candle.ts)
