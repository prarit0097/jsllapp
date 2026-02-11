from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Announcement, EventsFetchRun, NewsItem
from apps.events.nse import parse_nse_datetime_to_utc
from apps.events.services import fetch_announcements_nse
from apps.events.taxonomy import classify_announcement
from apps.events.utils import build_announcement_dedupe_key
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


class TaxonomyTests(TestCase):
    def test_classify_dividend(self):
        result = classify_announcement('Dividend declared for Q4')
        self.assertEqual(result['type'], 'dividend')
        self.assertEqual(result['polarity'], 1)
        self.assertGreater(result['impact_score'], 0)

    def test_classify_legal(self):
        result = classify_announcement('Company receives penalty notice')
        self.assertEqual(result['type'], 'legal')
        self.assertEqual(result['polarity'], -1)
        self.assertLess(result['impact_score'], 0)

    def test_classify_board_meeting(self):
        result = classify_announcement('Outcome of Board Meeting')
        self.assertEqual(result['type'], 'board_meeting')
        self.assertGreaterEqual(result['impact_score'], 25)
        self.assertFalse(result['low_priority'])

    def test_classify_results_strength(self):
        result = classify_announcement('Outcome of Board Meeting - Unaudited Financial Results Q3')
        self.assertIn(result['type'], {'results', 'board_meeting'})
        self.assertGreaterEqual(result['impact_score'], 25)
        self.assertFalse(result['low_priority'])

    def test_classify_results_low_priority_false(self):
        result = classify_announcement('Clarification - Financial Results')
        self.assertEqual(result['type'], 'results')
        self.assertFalse(result['low_priority'])

    def test_classify_insider(self):
        result = classify_announcement('Insider Trading - Others')
        self.assertEqual(result['type'], 'insider')
        self.assertTrue(result['low_priority'])
        self.assertLessEqual(result['impact_score'], 5)

    def test_classify_compliance(self):
        result = classify_announcement('Copy of Newspaper Publication')
        self.assertEqual(result['type'], 'compliance')
        self.assertLess(result['impact_score'], 10)
        self.assertTrue(result['low_priority'])


class AnnouncementTests(TestCase):
    def test_announcements_7d_count(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = timezone.now().astimezone(tz)
        Announcement.objects.create(
            published_at=now - timedelta(days=2),
            headline='Recent announcement',
            impact_score=20,
            low_priority=False,
        )
        Announcement.objects.create(
            published_at=now - timedelta(days=2),
            headline='Low impact announcement',
            impact_score=5,
            low_priority=True,
        )
        Announcement.objects.create(
            published_at=now - timedelta(days=10),
            headline='Old announcement',
            impact_score=20,
            low_priority=False,
        )
        response = self.client.get('/api/v1/jsll/events/summary')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['announcements_last_7d_count'], 1)

    def test_announcement_dedupe(self):
        tz = ZoneInfo('Asia/Kolkata')
        now = timezone.now().astimezone(tz)
        key = build_announcement_dedupe_key('JSLL', 'Duplicate announcement', now, '')
        Announcement.objects.create(
            published_at=now,
            headline='Duplicate announcement',
            dedupe_key=key,
        )
        with self.assertRaises(IntegrityError):
            Announcement.objects.create(
                published_at=now,
                headline='Duplicate announcement',
                dedupe_key=key,
            )

    def test_reclassify_command_sets_low_priority(self):
        Announcement.objects.create(
            published_at=timezone.now(),
            headline='Insider Trading - Others',
        )
        call_command('reclassify_announcements')
        ann = Announcement.objects.get()
        self.assertTrue(ann.low_priority)
        self.assertLessEqual(ann.impact_score, 5)

    def test_reclassify_clusters_results(self):
        now = timezone.now()
        Announcement.objects.create(
            published_at=now,
            headline='Outcome of Board Meeting - Unaudited Financial Results',
            type='results',
            impact_score=70,
            low_priority=False,
        )
        Announcement.objects.create(
            published_at=now + timedelta(minutes=1),
            headline='Outcome of Board Meeting - Unaudited Financial Results',
            type='results',
            impact_score=70,
            low_priority=False,
        )
        call_command('reclassify_announcements')
        kept = Announcement.objects.filter(low_priority=False, impact_score__gte=10)
        self.assertEqual(kept.count(), 1)

    @patch('apps.events.services.fetch_nse_announcements')
    def test_fetch_announcements_dedupe(self, mock_fetch):
        now = timezone.now()
        mock_fetch.return_value = [
            {'headline': 'Outcome of Board Meeting - Unaudited Financial Results', 'published_at': now, 'published_text': '11/02/2026, 04:11:00 PM', 'url': 'http://example.com/a.pdf'},
            {'headline': 'Outcome of Board Meeting - Unaudited Financial Results', 'published_at': now, 'published_text': '11/02/2026, 04:11:00 PM', 'url': 'http://example.com/a.pdf'},
        ]
        result = fetch_announcements_nse(symbol='JSLL')
        self.assertEqual(result['parsed_count'], 2)
        self.assertEqual(result['saved_count'], 1)
        self.assertEqual(Announcement.objects.count(), 1)
        result = fetch_announcements_nse(symbol='JSLL')
        self.assertEqual(result['parsed_count'], 2)
        self.assertEqual(result['saved_count'], 0)
        self.assertEqual(Announcement.objects.count(), 1)

    @patch('apps.events.services.fetch_nse_announcements')
    def test_fetch_announcements_idempotent(self, mock_fetch):
        now = timezone.now()
        mock_fetch.return_value = [
            {'headline': 'Outcome of Board Meeting', 'published_at': now, 'published_text': '11/02/2026, 04:11:00 PM', 'url': 'http://example.com/a.pdf'},
            {'headline': 'Outcome of Board Meeting', 'published_at': now, 'published_text': '11/02/2026, 04:11:00 PM', 'url': 'http://example.com/a.pdf'},
        ]
        first = fetch_announcements_nse(symbol='JSLL')
        self.assertEqual(first['saved_count'], 1)
        self.assertEqual(Announcement.objects.count(), 1)
        second = fetch_announcements_nse(symbol='JSLL')
        self.assertEqual(second['saved_count'], 0)
        self.assertEqual(Announcement.objects.count(), 1)

    def test_dedupe_prefers_results_over_other(self):
        base = timezone.now().replace(second=10, microsecond=0)
        url = 'http://example.com/doc.pdf'
        Announcement.objects.create(
            published_at=base,
            headline='Clarification',
            url=url,
            type='other',
            impact_score=0,
            low_priority=True,
        )
        Announcement.objects.create(
            published_at=base + timedelta(seconds=30),
            headline='Clarification - Financial Results',
            url=url,
            type='results',
            impact_score=70,
            low_priority=False,
        )
        call_command('dedupe_announcements')
        remaining = Announcement.objects.all()
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().type, 'results')

    def test_dedupe_key_rounds_timestamp_to_minute(self):
        base = timezone.now().replace(second=10, microsecond=0)
        later = base + timedelta(seconds=30)
        key1 = build_announcement_dedupe_key('JSLL', 'Outcome of Board Meeting', base, '')
        key2 = build_announcement_dedupe_key('JSLL', 'Outcome of Board Meeting', later, '')
        self.assertEqual(key1, key2)

    def test_unique_constraint_prevents_duplicates(self):
        now = timezone.now()
        key = build_announcement_dedupe_key('JSLL', 'Outcome of Board Meeting', now, 'http://example.com/a.pdf')
        Announcement.objects.create(
            published_at=now,
            headline='Outcome of Board Meeting',
            url='http://example.com/a.pdf',
            dedupe_key=key,
        )
        with self.assertRaises(IntegrityError):
            Announcement.objects.create(
                published_at=now + timedelta(seconds=5),
                headline='Outcome of Board Meeting',
                url='http://example.com/a.pdf',
                dedupe_key=key,
            )

    def test_parse_nse_datetime_formats(self):
        samples = [
            '10-Feb-2026 12:24:21',
            '09-Feb-2026 19:25:07',
            '11/02/2026, 04:11:00 pm',
            '11/02/2026 04:11:00 PM',
        ]
        for text in samples:
            dt = parse_nse_datetime_to_utc(text)
            self.assertIsNotNone(dt.tzinfo)

    def test_parse_nse_datetime_numeric_formats(self):
        dt1 = parse_nse_datetime_to_utc('10022026122421')
        self.assertIsNotNone(dt1.tzinfo)
        dt2 = parse_nse_datetime_to_utc('09022026192507')
        self.assertIsNotNone(dt2.tzinfo)

    def test_parse_nse_datetime_numeric_invalid_length(self):
        with self.assertRaises(ValueError):
            parse_nse_datetime_to_utc('123')

    @patch('apps.events.services.fetch_nse_announcements')
    def test_invalid_published_text_skips_row(self, mock_fetch):
        mock_fetch.return_value = [
            {'headline': 'Bad date row', 'published_at': None, 'published_text': 'BAD DATE', 'url': 'http://example.com/a.pdf'},
        ]
        result = fetch_announcements_nse(symbol='JSLL')
        self.assertEqual(result['parsed_count'], 1)
        self.assertEqual(result['saved_count'], 0)
        self.assertEqual(result['parse_errors'], 1)
        self.assertEqual(Announcement.objects.count(), 0)


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


class EventsApiTests(APITestCase):
    def test_news_endpoint(self):
        NewsItem.objects.create(
            published_at=timezone.now(),
            source='test',
            title='Test news',
            url='https://example.com/test-news',
            summary='summary',
            sentiment=0.1,
            relevance=1.0,
            entities_json={},
        )
        response = self.client.get('/api/v1/jsll/news?limit=10')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) >= 1)

    def test_events_summary(self):
        Announcement.objects.create(
            published_at=timezone.now(),
            headline='High impact announcement',
            impact_score=20,
            low_priority=False,
        )
        Announcement.objects.create(
            published_at=timezone.now(),
            headline='Low impact',
            impact_score=0,
            low_priority=True,
        )
        EventsFetchRun.objects.create(news_ok=True, announcements_ok=True)
        response = self.client.get('/api/v1/jsll/events/summary')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['announcements_last_7d_count'], 1)
        self.assertEqual(payload['announcements_high_impact_7d_count'], 1)
        self.assertIn('news_last_24h_count', payload)
        self.assertIn('news_last_24h_sentiment_avg', payload)
        self.assertIn('announcements_last_24h_count', payload)
        self.assertIn('announcements_impact_sum_24h', payload)
        self.assertIn('announcements_impact_sum_7d', payload)
        self.assertIn('announcements_negative_impact_sum_7d', payload)
        self.assertIn('latest_high_impact', payload)
        self.assertIn('last_fetch_run', payload)
        self.assertEqual(payload['latest_high_impact']['headline'], 'High impact announcement')
        self.assertIn('published_at_ist', payload['latest_high_impact'])

    def test_openapi_docs(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertEqual(self.client.get('/api/docs/').status_code, 200)
        self.assertEqual(self.client.get('/api/redoc/').status_code, 200)
