from django.core.management.base import BaseCommand

from apps.predictions.services import generate_latest_predictions, invalidate_model_cache, run_backtest_and_store


class Command(BaseCommand):
    help = 'Generate latest predictions once.'

    def add_arguments(self, parser):
        parser.add_argument('--backtest', action='store_true', help='Run backtest after predictions')
        parser.add_argument('--force-retrain', action='store_true', help='Force model retrain (ignore cache)')

    def handle(self, *args, **options):
        force = options.get('force_retrain', False)
        if force:
            invalidate_model_cache()
        preds = generate_latest_predictions(force_retrain=force)
        self.stdout.write(f'Predictions generated: {len(preds)}')
        if options.get('backtest'):
            run = run_backtest_and_store()
            if run:
                self.stdout.write('Backtest run stored')
            else:
                self.stdout.write('Backtest skipped (insufficient data)')
