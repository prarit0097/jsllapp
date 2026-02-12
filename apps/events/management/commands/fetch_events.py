from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import EventsFetchRun
from apps.events.services import fetch_announcements_nse, fetch_news_rss


class Command(BaseCommand):
    help = 'Fetch JSLL events news and announcements.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reclassify',
            action='store_true',
            help='Run reclassify_announcements after fetching events.',
        )

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

        ann_summary = None
        try:
            ann_result = fetch_announcements_nse()
            parsed = ann_result['parsed_count']
            created = ann_result['saved_count']
            updated = ann_result['updated_count']
            skipped = ann_result['skipped_duplicates']
            parse_errors = ann_result['parse_errors']
            errors = ann_result['errors']
            total_processed = created + updated + skipped + parse_errors

            run.announcements_fetched = created + updated
            run.announcements_ok = total_processed > 0 and not errors
            if errors:
                notes.append(f"announcements_error: {','.join(errors)}")
            notes.append(
                "ann_parsed={parsed}, ann_created={created}, ann_updated={updated}, "
                "ann_skipped={skipped}, ann_parse_errors={parse_errors}, ann_total_processed={total_processed}"
                .format(
                    parsed=parsed,
                    created=created,
                    updated=updated,
                    skipped=skipped,
                    parse_errors=parse_errors,
                    total_processed=total_processed,
                )
            )
            ann_summary = {
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'parse_errors': parse_errors,
                'total_processed': total_processed,
            }
        except Exception as exc:
            notes.append(f"announcements_error: {exc}")

        run.finished_at = timezone.now()
        run.notes = '; '.join(notes)
        run.save()

        self.stdout.write('Events fetch summary')
        self.stdout.write(f"News OK: {run.news_ok} ({run.news_fetched})")
        if ann_summary:
            self.stdout.write(
                "Announcements OK: {ok} (created={created}, updated={updated}, skipped={skipped}, "
                "parse_errors={parse_errors}, total_processed={total_processed})".format(
                    ok=run.announcements_ok,
                    created=ann_summary['created'],
                    updated=ann_summary['updated'],
                    skipped=ann_summary['skipped'],
                    parse_errors=ann_summary['parse_errors'],
                    total_processed=ann_summary['total_processed'],
                )
            )
        else:
            self.stdout.write(f"Announcements OK: {run.announcements_ok} ({run.announcements_fetched})")
        if run.notes:
            self.stdout.write(f"Notes: {run.notes}")

        if options.get('reclassify'):
            call_command('reclassify_announcements')
