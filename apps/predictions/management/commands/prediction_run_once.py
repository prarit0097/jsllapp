from django.core.management.base import BaseCommand

from apps.predictions.services import generate_latest_predictions, run_backtest_and_store


class Command(BaseCommand):
    help = 'Generate latest predictions once.'

    def add_arguments(self, parser):
        parser.add_argument('--backtest', action='store_true', help='Run backtest after predictions')

    def handle(self, *args, **options):
        preds = generate_latest_predictions()
        self.stdout.write(f'Predictions generated: {len(preds)}')
        if options.get('backtest'):
            run = run_backtest_and_store()
            if run:
                self.stdout.write('Backtest run stored')
            else:
                self.stdout.write('Backtest skipped (insufficient data)')
