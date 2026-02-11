from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.events.models import Announcement
from apps.events.taxonomy import compute_dedupe_hash


class Command(BaseCommand):
    help = 'Delete duplicate announcements based on dedupe_hash.'

    def handle(self, *args, **options):
        total_before = Announcement.objects.count()
        by_hash = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            ann.dedupe_hash = compute_dedupe_hash(ann.headline, ann.published_at, ann.url)
            ann.save(update_fields=['dedupe_hash'])
            by_hash[ann.dedupe_hash].append(ann)

        deleted = 0
        for items in by_hash.values():
            if len(items) <= 1:
                continue
            items_sorted = sorted(items, key=lambda x: (x.impact_score, x.published_at), reverse=True)
            to_delete = items_sorted[1:]
            Announcement.objects.filter(id__in=[a.id for a in to_delete]).delete()
            deleted += len(to_delete)

        total_after = Announcement.objects.count()
        self.stdout.write(f"Before: {total_before}")
        self.stdout.write(f"Deleted: {deleted}")
        self.stdout.write(f"After: {total_after}")
