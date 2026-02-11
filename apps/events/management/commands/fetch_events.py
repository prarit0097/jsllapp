from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import EventsFetchRun
from apps.events.services import fetch_announcements_nse, fetch_news_rss


class Command(BaseCommand):
    help = 'Fetch JSLL events news and announcements.'

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

        try:
            ann_count, note = fetch_announcements_nse()
            run.announcements_fetched = ann_count
            run.announcements_ok = ann_count > 0
            if note:
                notes.append(note)
        except Exception as exc:
            notes.append(f"announcements_error: {exc}")

        run.finished_at = timezone.now()
        run.notes = '; '.join(notes)
        run.save()

        self.stdout.write('Events fetch summary')
        self.stdout.write(f"News OK: {run.news_ok} ({run.news_fetched})")
        self.stdout.write(f"Announcements OK: {run.announcements_ok} ({run.announcements_fetched})")
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")