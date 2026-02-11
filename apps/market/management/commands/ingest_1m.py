from django.core.management.base import BaseCommand

from apps.market.providers.stooq_provider import StooqProvider
from apps.market.providers.yfinance_provider import YFinanceProvider
from apps.market.services import ingest_1m_candles_multi


class Command(BaseCommand):
    help = 'Ingest 1m candles using primary and fallback providers.'

    def handle(self, *args, **options):
        primary = YFinanceProvider()
        fallback = StooqProvider()

        run = ingest_1m_candles_multi(primary, fallback)

        self.stdout.write('Ingestion summary')
        self.stdout.write(f"Primary OK: {run.primary_ok} ({run.candles_fetched_primary})")
        self.stdout.write(f"Fallback OK: {run.fallback_ok} ({run.candles_fetched_fallback})")
        self.stdout.write(f"Candles saved: {run.candles_saved}")
        self.stdout.write(f"Missing filled: {run.missing_filled}")
        self.stdout.write(f"Outliers rejected: {run.outliers_rejected}")
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")