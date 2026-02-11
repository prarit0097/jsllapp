from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import Announcement
from apps.events.taxonomy import classify_announcement, compute_dedupe_hash


class Command(BaseCommand):
    help = 'Reclassify announcements and set dedupe_hash/low_priority.'

    def handle(self, *args, **options):
        total = Announcement.objects.count()
        by_day_results = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            classification = classify_announcement(ann.headline)
            ann.type = classification['type']
            ann.polarity = classification['polarity']
            ann.impact_score = classification['impact_score']
            ann.low_priority = classification['low_priority']
            ann.dedupe_hash = compute_dedupe_hash(ann.headline, ann.published_at, ann.type)
            ann.tags_json = {'tags': classification['tags']}
            ann.save(update_fields=['type', 'polarity', 'impact_score', 'low_priority', 'dedupe_hash', 'tags_json'])

            if ann.type == 'results':
                by_day_results[ann.published_at.date()].append(ann)

        for items in by_day_results.values():
            items_sorted = sorted(items, key=lambda x: x.impact_score, reverse=True)
            for duplicate in items_sorted[1:]:
                if not duplicate.low_priority:
                    duplicate.low_priority = True
                    duplicate.save(update_fields=['low_priority'])

        high_impact_7d = Announcement.objects.filter(impact_score__gte=10, low_priority=False)
        latest = high_impact_7d.order_by('-published_at').first()

        self.stdout.write(f"Total announcements: {total}")
        self.stdout.write(f"High impact (7d): {high_impact_7d.count()}")
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
