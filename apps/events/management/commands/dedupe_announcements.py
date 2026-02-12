from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.events.models import Announcement
from apps.events.utils import build_announcement_dedupe_key, build_soft_dedupe_key


def _score(ann):
    type_bonus = 100 if ann.type == 'results' else (50 if ann.type == 'board_meeting' else 0)
    return ann.impact_score * 10 + type_bonus + (20 if not ann.low_priority else 0)


class Command(BaseCommand):
    help = 'Delete duplicate announcements based on dedupe_key.'

    def handle(self, *args, **options):
        total_before = Announcement.objects.count()
        symbol = getattr(settings, 'JSLL_TICKER', 'JSLL')
        by_key = defaultdict(list)

        for ann in Announcement.objects.all().iterator():
            soft_key = build_soft_dedupe_key(symbol, ann.published_at, ann.url)
            key = soft_key or ann.dedupe_key
            if not key:
                key = build_announcement_dedupe_key(symbol, ann.headline, ann.published_at, ann.url, '')
            if not key:
                continue
            by_key[key].append(ann)

        to_delete = []
        to_keep = []
        top_dupes = sorted(((k, len(v)) for k, v in by_key.items()), key=lambda x: x[1], reverse=True)

        for key, items in by_key.items():
            items_sorted = sorted(items, key=lambda x: (x.published_at, _score(x)), reverse=True)
            keep = items_sorted[0]
            to_keep.append((keep.id, key))
            to_delete.extend([item.id for item in items_sorted[1:]])

        if to_delete:
            Announcement.objects.filter(id__in=to_delete).delete()

        for ann_id, key in to_keep:
            Announcement.objects.filter(id=ann_id).update(dedupe_key=key)

        total_after = Announcement.objects.count()
        deleted = total_before - total_after
        self.stdout.write(f"Before: {total_before}")
        self.stdout.write(f"Deleted: {deleted}")
        self.stdout.write(f"After: {total_after}")
        self.stdout.write("Top duplicate keys:")
        for key, count in top_dupes[:5]:
            if count > 1:
                self.stdout.write(f"- {key}: {count}")
