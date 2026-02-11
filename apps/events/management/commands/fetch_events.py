from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import EventsFetchRun
from apps.events.services import fetch_news_rss


class Command(BaseCommand):
    help = 'Fetch JSLL events news via RSS.'

    def handle(self, *args, **options):
        run = EventsFetchRun.objects.create()
        notes = []
        try:
            news_count, note = fetch_news_rss()
            run.news_fetched = news_count
            run.news_ok = news_count > 0
            if note:
                notes.append(note)
        except Exception as exc:
            notes.append(f"news_error: {exc}")

        run.finished_at = timezone.now()
        run.notes = '; '.join(notes)
        run.save()

        self.stdout.write('Events fetch summary')
        self.stdout.write(f"News OK: {run.news_ok} ({run.news_fetched})")
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")