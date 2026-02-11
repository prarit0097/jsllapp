from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.market.data_quality import DataQualityEngine
from apps.market.market_time import (
    compute_thresholds,
    is_near_close,
    is_within_today_session_end,
    market_state,
)
from apps.market.models import IngestRun, Ohlc1m
from apps.market.providers.mock_provider import MockPriceProvider
from apps.market.reconcile import reconcile_batches
from apps.market.services import ingest_1m_candles, ingest_1m_candles_multi
from apps.market.tasks import is_market_open


class DummyProvider:
    def __init__(self, candles):
        self._candles = candles

    def fetch_latest_1m(self):
        return list(self._candles)


class MarketTimeTests(TestCase):
    def test_market_state_open(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = datetime(2026, 2, 11, 10, 0, tzinfo=tz)
        self.assertEqual(market_state(now), 'OPEN')

    def test_market_state_closed(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = datetime(2026, 2, 11, 20, 0, tzinfo=tz)
        self.assertEqual(market_state(now), 'CLOSED')

    def test_near_close(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = datetime(2026, 2, 11, 15, 25, tzinfo=tz)
        self.assertTrue(is_near_close(now))

    def test_thresholds(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = datetime(2026, 2, 11, 10, 0, tzinfo=tz)
        freshness, min_candles = compute_thresholds(now)
        self.assertEqual(freshness, 180)
        self.assertEqual(min_candles, 45)

    def test_within_today_session_end(self):
        tz = ZoneInfo('Asia/Kolkata')
        dt = datetime(2026, 2, 11, 15, 30, tzinfo=tz)
        self.assertTrue(is_within_today_session_end(dt))


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

    def test_is_market_open_basic(self):
        now = timezone.now().replace(hour=10, minute=0)
        self.assertTrue(is_market_open(now))