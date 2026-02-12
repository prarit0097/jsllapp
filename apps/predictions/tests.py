from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.market.models import Ohlc1m
from .services import build_features_dataframe, build_labels, generate_latest_predictions


class PredictionFeatureLabelTests(TestCase):
    def _create_candles(self, start_ts, count, start_price=100.0):
        rows = []
        for i in range(count):
            price = start_price + i
            rows.append(
                Ohlc1m(
                    ts=start_ts + timedelta(minutes=i),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=100.0,
                    source='test',
                )
            )
        Ohlc1m.objects.bulk_create(rows)

    def test_label_alignment_1h(self):
        base = timezone.now().replace(second=0, microsecond=0) - timedelta(hours=2)
        self._create_candles(base, 70, start_price=100.0)
        df = build_features_dataframe(base, base + timedelta(minutes=69))
        df = build_labels(df)
        first = df.iloc[0]
        expected = (160.0 / 100.0) - 1.0
        self.assertAlmostEqual(first['y_1h'], expected, places=6)

    def test_next_trading_day_close(self):
        ist = ZoneInfo('Asia/Kolkata')
        base_ist = datetime(2026, 2, 10, 10, 0, tzinfo=ist)
        day1 = base_ist.astimezone(dt_timezone.utc)
        day2 = (base_ist + timedelta(days=1)).astimezone(dt_timezone.utc)

        self._create_candles(day1, 3, start_price=100.0)
        self._create_candles(day2, 3, start_price=120.0)

        df = build_features_dataframe(day1, day2 + timedelta(minutes=2))
        df = build_labels(df)
        first = df.iloc[0]
        expected = (122.0 / 100.0) - 1.0
        self.assertAlmostEqual(first['y_1d'], expected, places=6)


class PredictionApiTests(TestCase):
    def test_predictions_latest_endpoint(self):
        base = timezone.now().replace(second=0, microsecond=0) - timedelta(hours=3)
        for i in range(200):
            price = 100.0 + i * 0.1
            Ohlc1m.objects.create(
                ts=base + timedelta(minutes=i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=100.0,
                source='test',
            )

        generate_latest_predictions()
        response = self.client.get('/api/predictions/latest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('predictions', data)
        self.assertEqual(len(data['predictions']), 4)
