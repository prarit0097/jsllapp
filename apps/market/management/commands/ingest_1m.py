from django.core.management.base import BaseCommand

from apps.market.providers.yfinance_download_provider import YFinanceDownloadProvider
from apps.market.providers.yfinance_provider import YFinanceHistoryProvider
from apps.market.services import ingest_1m_candles_multi


class Command(BaseCommand):
    help = 'Ingest 1m candles using primary and fallback providers.'

    def handle(self, *args, **options):
        primary = YFinanceHistoryProvider()
        fallback = YFinanceDownloadProvider()

        run = ingest_1m_candles_multi(primary, fallback)

        self.stdout.write('Ingestion summary')
        self.stdout.write(f"Primary OK: {run.primary_ok} ({run.candles_fetched_primary})")
        self.stdout.write(f"Fallback OK: {run.fallback_ok} ({run.candles_fetched_fallback})")
        self.stdout.write(f"Candles saved: {run.candles_saved}")
        self.stdout.write(f"Missing filled: {run.missing_filled}")
        self.stdout.write(f"Outliers rejected: {run.outliers_rejected}")
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")