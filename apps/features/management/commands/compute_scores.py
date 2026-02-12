from django.core.management.base import BaseCommand

from apps.features.services import compute_latest_missing


class Command(BaseCommand):
    help = 'Compute latest missing feature scores.'

    def handle(self, *args, **options):
        result = compute_latest_missing()
        if result is None:
            self.stdout.write('No candle data available.')
            return
        self.stdout.write(f"Computed score for {result.ts}")
