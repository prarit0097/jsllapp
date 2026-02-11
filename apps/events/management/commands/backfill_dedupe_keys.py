from django.conf import settings
from django.core.management.base import BaseCommand

from apps.events.models import Announcement
from apps.events.utils import build_announcement_dedupe_key, build_soft_dedupe_key


def _score(ann):
    type_bonus = 100 if ann.type == 'results' else (50 if ann.type == 'board_meeting' else 0)
    return ann.impact_score * 10 + type_bonus + (20 if not ann.low_priority else 0)


class Command(BaseCommand):
    help = 'Backfill dedupe_key for announcements and drop duplicates.'

    def handle(self, *args, **options):
        symbol = getattr(settings, 'JSLL_TICKER', 'JSLL')
        before = Announcement.objects.count()
        by_key = {}

        for ann in Announcement.objects.all().iterator():
            soft_key = build_soft_dedupe_key(symbol, ann.published_at, ann.url)
            key = soft_key or build_announcement_dedupe_key(symbol, ann.headline, ann.published_at, ann.url, '')
            if not key:
                continue
            by_key.setdefault(key, []).append(ann)

        to_delete = []
        to_keep = []

        for key, items in by_key.items():
            items_sorted = sorted(items, key=lambda x: (_score(x), x.published_at), reverse=True)
            keep = items_sorted[0]
            to_keep.append((keep.id, key))
            to_delete.extend([item.id for item in items_sorted[1:]])

        if to_delete:
            Announcement.objects.filter(id__in=to_delete).delete()

        for ann_id, key in to_keep:
            Announcement.objects.filter(id=ann_id).update(dedupe_key=key)

        after = Announcement.objects.count()
        deleted = before - after
        self.stdout.write(f"Before: {before}")
        self.stdout.write(f"Deleted: {deleted}")
        self.stdout.write(f"After: {after}")
