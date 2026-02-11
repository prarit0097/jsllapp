from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.events.models import Announcement
from apps.events.taxonomy import compute_dedupe_hash


def _score(ann):
    return ann.impact_score * 10 + (100 if ann.type == 'results' else 0) + (20 if not ann.low_priority else 0)


class Command(BaseCommand):
    help = 'Delete duplicate announcements based on dedupe_hash.'

    def handle(self, *args, **options):
        total_before = Announcement.objects.count()
        by_hash = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            dedupe_hash = compute_dedupe_hash(ann.headline, ann.published_at, ann.url)
            by_hash[dedupe_hash].append(ann)

        to_delete = []
        to_keep = []
        for items in by_hash.values():
            items_sorted = sorted(items, key=lambda x: (_score(x), x.published_at), reverse=True)
            to_keep.append((items_sorted[0].id, items_sorted[0]))
            to_delete.extend([item.id for item in items_sorted[1:]])

        if to_delete:
            Announcement.objects.filter(id__in=to_delete).delete()

        for ann_id, ann in to_keep:
            dedupe_hash = compute_dedupe_hash(ann.headline, ann.published_at, ann.url)
            Announcement.objects.filter(id=ann_id).update(dedupe_hash=dedupe_hash)

        total_after = Announcement.objects.count()
        deleted = total_before - total_after
        self.stdout.write(f"Before: {total_before}")
        self.stdout.write(f"Deleted: {deleted}")
        self.stdout.write(f"After: {total_after}")
