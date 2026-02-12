from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.market.models import Ohlc1m

from .models import SignalScore
from .services import compute_latest_missing


class FeatureStoreTests(TestCase):
    def test_compute_latest_missing_creates_score(self):
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
        result = compute_latest_missing()
        self.assertIsNotNone(result)
        self.assertEqual(SignalScore.objects.count(), 1)


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
