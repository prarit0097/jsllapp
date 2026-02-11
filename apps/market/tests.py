from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.market.data_quality import DataQualityEngine
from apps.market.models import IngestRun, Ohlc1m
from apps.market.providers.mock_provider import MockPriceProvider
from apps.market.reconcile import reconcile_batches
from apps.market.services import ingest_1m_candles, ingest_1m_candles_multi


class DummyProvider:
    def __init__(self, candles):
        self._candles = candles

    def fetch_latest_1m(self):
        return list(self._candles)


class IngestionTests(TestCase):
    def test_ingest_with_mock_provider_creates_candles(self):
        provider = MockPriceProvider()
        created = ingest_1m_candles(provider)
        self.assertGreater(created, 0)
        self.assertEqual(Ohlc1m.objects.count(), created)

    def test_duplicate_ingest_does_not_duplicate(self):
        provider = MockPriceProvider()
        ingest_1m_candles(provider)
        first_count = Ohlc1m.objects.count()
        ingest_1m_candles(provider)
        self.assertEqual(Ohlc1m.objects.count(), first_count)

    def test_outlier_detection(self):
        engine = DataQualityEngine(max_jump_pct=0.10)
        now = timezone.now().replace(second=0, microsecond=0)
        prev = {
            'ts': now,
            'open': 100.0,
            'high': 100.0,
            'low': 100.0,
            'close': 100.0,
            'volume': 10.0,
            'source': 'test',
        }
        outlier = {
            'ts': now + timedelta(minutes=1),
            'open': 120.0,
            'high': 120.0,
            'low': 120.0,
            'close': 120.0,
            'volume': 10.0,
            'source': 'test',
        }
        self.assertTrue(engine.detect_outliers(outlier, prev))

    def test_reconcile_missing_primary_uses_fallback(self):
        now = timezone.now().replace(second=0, microsecond=0)
        primary = [
            {
                'ts': now,
                'open': 100.0,
                'high': 101.0,
                'low': 99.0,
                'close': 100.5,
                'volume': 10.0,
            }
        ]
        fallback = [
            {
                'ts': now,
                'open': 100.0,
                'high': 101.0,
                'low': 99.0,
                'close': 100.5,
                'volume': 10.0,
            },
            {
                'ts': now + timedelta(minutes=1),
                'open': 101.0,
                'high': 102.0,
                'low': 100.0,
                'close': 101.5,
                'volume': 12.0,
            },
        ]
        merged = reconcile_batches(primary, fallback)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]['source'], 'fallback')

    def test_ingest_multi_creates_run_and_candles(self):
        now = timezone.now().replace(second=0, microsecond=0)
        candles = [
            {
                'ts': now,
                'open': 100.0,
                'high': 101.0,
                'low': 99.0,
                'close': 100.5,
                'volume': 10.0,
                'source': 'primary',
            },
            {
                'ts': now + timedelta(minutes=1),
                'open': 101.0,
                'high': 102.0,
                'low': 100.0,
                'close': 101.5,
                'volume': 12.0,
                'source': 'primary',
            },
        ]
        primary = DummyProvider(candles)
        fallback = DummyProvider([])
        run = ingest_1m_candles_multi(primary, fallback)
        self.assertEqual(IngestRun.objects.count(), 1)
        self.assertGreater(Ohlc1m.objects.count(), 0)
        self.assertTrue(run.primary_ok)