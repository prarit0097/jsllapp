from django.core.management.base import BaseCommand

from apps.market.providers.yfinance_download_provider import YFinanceDownloadProvider
from apps.market.providers.yfinance_provider import YFinanceHistoryProvider
from apps.market.services import ingest_1m_candles_multi


class Command(BaseCommand):
    help = 'Ingest 1m candles using primary and fallback providers.'

    def handle(self, *args, **options):
        primary = YFinanceHistoryProvider()
        fallback = YFinanceDownloadProvider()

        run, meta = ingest_1m_candles_multi(primary, fallback)

        self.stdout.write('Ingestion summary')
        self.stdout.write(f"Primary OK: {run.primary_ok} ({run.candles_fetched_primary})")
        self.stdout.write(f"Fallback OK: {run.fallback_ok} ({run.candles_fetched_fallback})")
        self.stdout.write(f"Candles saved: {run.candles_saved}")
        self.stdout.write(f"Missing filled: {run.missing_filled}")
        self.stdout.write(f"Outliers rejected: {run.outliers_rejected}")
        if meta.get('fetched_end_ts'):
            self.stdout.write(f"Fetched end ts: {meta.get('fetched_end_ts')}")
        if meta.get('provider_delay_sec') is not None:
            self.stdout.write(f"Provider delay sec: {meta.get('provider_delay_sec')}")
        if meta.get('no_new_candles'):
            self.stdout.write('No new candles')
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")
