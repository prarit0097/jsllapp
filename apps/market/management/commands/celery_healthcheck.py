from datetime import timedelta

from celery.exceptions import TimeoutError
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import EventsFetchRun
from apps.features.models import SignalScore
from apps.market.models import IngestRun, Ohlc1m
from config.celery import app


class Command(BaseCommand):
    help = 'Check Celery broker/worker health and data freshness.'

    def handle(self, *args, **options):
        broker_ok = False
        worker_ok = False
        ping_result = None

        try:
            with app.connection_or_acquire() as conn:
                conn.ensure_connection(max_retries=1)
            broker_ok = True
        except Exception as exc:
            self.stdout.write(f"Broker check failed: {exc}")

        try:
            ping_result = app.control.ping(timeout=2.0)
            worker_ok = bool(ping_result)
        except TimeoutError:
            self.stdout.write('Worker ping timeout')
        except Exception as exc:
            self.stdout.write(f"Worker ping failed: {exc}")

        last_ingest = IngestRun.objects.first()
        last_events = EventsFetchRun.objects.first()
        last_score = SignalScore.objects.order_by('-ts').first()
        latest_candle = Ohlc1m.objects.order_by('-ts').first()
        now = timezone.now()
        freshness_sec = None
        if latest_candle:
            freshness_sec = int((now - latest_candle.ts).total_seconds())

        self.stdout.write('Celery healthcheck')
        self.stdout.write(f"Broker OK: {broker_ok}")
        self.stdout.write(f"Worker OK: {worker_ok}")
        if ping_result is not None:
            self.stdout.write(f"Ping result: {ping_result}")

        self.stdout.write('Last runs')
        self.stdout.write(
            f"IngestRun: {last_ingest.finished_at if last_ingest else None}"
        )
        self.stdout.write(
            f"EventsFetchRun: {last_events.finished_at if last_events else None}"
        )
        self.stdout.write(
            f"SignalScore: {last_score.ts if last_score else None}"
        )
        self.stdout.write(
            f"Latest candle ts: {latest_candle.ts if latest_candle else None}"
        )
        self.stdout.write(
            f"Candle freshness sec: {freshness_sec}"
        )
