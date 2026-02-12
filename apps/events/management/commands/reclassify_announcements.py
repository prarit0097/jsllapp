from collections import defaultdict
import sys

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import Announcement
from apps.events.taxonomy import classify_announcement
from apps.events.utils import build_announcement_dedupe_key
from apps.events.services import high_impact_queryset


def _normalize(text):
    return ' '.join((text or '').lower().split())


def _is_testing():
    return 'test' in sys.argv


class Command(BaseCommand):
    help = 'Reclassify announcements and set dedupe_key/low_priority.'

    def _should_print(self):
        if _is_testing() and getattr(self.stdout, '_out', None) is sys.stdout:
            return False
        return True

    def handle(self, *args, **options):
        total = Announcement.objects.count()
        by_results_key = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            classification = classify_announcement(ann.headline)
            ann.type = classification['type']
            ann.polarity = classification['polarity']
            ann.impact_score = classification['impact_score']
            ann.low_priority = classification['low_priority']
            ann.tags_json = {'tags': classification['tags']}

            dedupe_key = build_announcement_dedupe_key('', ann.headline, ann.published_at, ann.url, '')
            if dedupe_key:
                exists = Announcement.objects.filter(dedupe_key=dedupe_key).exclude(id=ann.id).exists()
                if not exists:
                    ann.dedupe_key = dedupe_key

            ann.save(update_fields=['type', 'polarity', 'impact_score', 'low_priority', 'tags_json', 'dedupe_key'])

            if ann.type == 'results':
                key = (ann.published_at.date().isoformat(), _normalize(ann.headline))
                by_results_key[key].append(ann)

        for items in by_results_key.values():
            items_sorted = sorted(items, key=lambda x: (x.impact_score, x.published_at), reverse=True)
            for duplicate in items_sorted[1:]:
                if not duplicate.low_priority or duplicate.impact_score != 0:
                    duplicate.low_priority = True
                    duplicate.impact_score = 0
                    duplicate.save(update_fields=['low_priority', 'impact_score'])

        high_impact_rolling = high_impact_queryset(days=7)
        high_impact_calendar = high_impact_queryset(days=7, use_calendar_days=True)
        latest = high_impact_rolling.order_by('-published_at').first()

        if self._should_print():
            self.stdout.write(f"Total announcements: {total}")
            self.stdout.write(f"High impact (7d, rolling_168h): {high_impact_rolling.count()}")
            self.stdout.write(f"High impact (7d, calendar_days): {high_impact_calendar.count()}")
            if latest:
                ist = timezone.localtime(latest.published_at)
                self.stdout.write(
                    f"Latest high impact: {latest.headline} (UTC={latest.published_at}, IST={ist})"
                )

            self.stdout.write("\nMost recent announcements (top 15):")
            recent = Announcement.objects.order_by('-published_at')[:15]
            for ann in recent:
                ist = timezone.localtime(ann.published_at)
                self.stdout.write(
                    f"- {ann.published_at} / IST {ist} | {ann.type} | impact={ann.impact_score} | low={ann.low_priority} | {ann.headline}"
                )

            keywords = ('outcome of board meeting', 'unaudited', 'financial results')
            matches = [
                ann for ann in Announcement.objects.all().iterator()
                if any(key in ann.headline.lower() for key in keywords)
            ]
            self.stdout.write("\nMatches for board meeting/results keywords:")
            if not matches:
                self.stdout.write("- None found in DB")
            for ann in matches:
                ist = timezone.localtime(ann.published_at)
                self.stdout.write(
                    f"- {ann.published_at} / IST {ist} | {ann.type} | impact={ann.impact_score} | low={ann.low_priority} | {ann.headline}"
                )
