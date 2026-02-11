from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.events.models import Announcement
from apps.events.taxonomy import compute_dedupe_hash, compute_soft_key


def _score(ann):
    type_bonus = 100 if ann.type == 'results' else (50 if ann.type == 'board_meeting' else 0)
    return ann.impact_score * 10 + type_bonus + (20 if not ann.low_priority else 0)


class Command(BaseCommand):
    help = 'Delete duplicate announcements based on dedupe_hash.'

    def handle(self, *args, **options):
        total_before = Announcement.objects.count()
        symbol = getattr(settings, 'JSLL_TICKER', 'JSLL')
        by_key = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            soft_key = compute_soft_key(ann.published_at, ann.url, symbol)
            key = soft_key or compute_dedupe_hash(ann.headline, ann.published_at, ann.url, symbol)
            by_key[key].append(ann)

        to_delete = []
        to_keep = []
        top_dupes = sorted(((k, len(v)) for k, v in by_key.items()), key=lambda x: x[1], reverse=True)

        for items in by_key.values():
            items_sorted = sorted(items, key=lambda x: (_score(x), x.published_at), reverse=True)
            to_keep.append((items_sorted[0].id, items_sorted[0]))
            to_delete.extend([item.id for item in items_sorted[1:]])

        if to_delete:
            Announcement.objects.filter(id__in=to_delete).delete()

        for ann_id, ann in to_keep:
            dedupe_hash = compute_dedupe_hash(ann.headline, ann.published_at, ann.url, symbol)
            Announcement.objects.filter(id=ann_id).update(dedupe_hash=dedupe_hash)

        total_after = Announcement.objects.count()
        deleted = total_before - total_after
        self.stdout.write(f"Before: {total_before}")
        self.stdout.write(f"Deleted: {deleted}")
        self.stdout.write(f"After: {total_after}")
        self.stdout.write("Top duplicate keys:")
        for key, count in top_dupes[:5]:
            if count > 1:
                self.stdout.write(f"- {key}: {count}")
