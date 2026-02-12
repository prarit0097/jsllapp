from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Announcement
from apps.market.models import Ohlc1m

from .compute import compute_features_for_ts
from .models import SignalScore
from .scoring import score_from_features
from .services import compute_latest_missing


class FeatureStoreTests(TestCase):
    def _seed_candles(self, start_ts, count=30):
        candles = []
        price = 100.0
        for i in range(count):
            ts = start_ts + timedelta(minutes=i)
            open_price = price
            close_price = price * (1.001 if i % 3 != 0 else 0.999)
            high = max(open_price, close_price) * 1.001
            low = min(open_price, close_price) * 0.999
            volume = 100 + i * 2
            candles.append(
                Ohlc1m(
                    ts=ts,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close_price,
                    volume=volume,
                    source='test',
                )
            )
            price = close_price
        Ohlc1m.objects.bulk_create(candles)
        return candles[-1].ts

    def test_compute_latest_missing_creates_score(self):
        now = timezone.now().replace(second=0, microsecond=0)
        self._seed_candles(now, count=30)
        result = compute_latest_missing()
        self.assertIsNotNone(result)
        self.assertEqual(SignalScore.objects.count(), 1)
        self.assertNotEqual(result.overall_score, 50)

    def test_leakage_prevention_announcements(self):
        now = timezone.now().replace(second=0, microsecond=0)
        last_ts = self._seed_candles(now, count=30)
        Announcement.objects.create(
            published_at=last_ts - timedelta(hours=1),
            headline='Financial Results Update',
            impact_score=30,
            low_priority=False,
            type='results',
        )
        Announcement.objects.create(
            published_at=last_ts + timedelta(hours=1),
            headline='Future Financial Results',
            impact_score=50,
            low_priority=False,
            type='results',
        )
        features = compute_features_for_ts(last_ts)
        self.assertEqual(features['ann_impact_sum_24h'], 30)
        self.assertEqual(features['ann_results_flag_7d'], 1)

    def test_score_ranges(self):
        now = timezone.now().replace(second=0, microsecond=0)
        last_ts = self._seed_candles(now, count=30)
        features = compute_features_for_ts(last_ts)
        scores = score_from_features(features)
        for key in [
            'price_action_score',
            'volume_score',
            'news_score',
            'announcements_score',
            'regime_score',
            'overall_score',
        ]:
            self.assertGreaterEqual(scores[key], 0)
            self.assertLessEqual(scores[key], 100)


class FeatureApiTests(APITestCase):
    def test_scores_latest_endpoint(self):
        now = timezone.now().replace(second=0, microsecond=0)
        Ohlc1m.objects.create(
            ts=now,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            source='test',
        )
        compute_latest_missing()
        response = self.client.get('/api/v1/jsll/scores/latest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('scores', payload)
        self.assertIn('overall', payload.get('scores', {}))
