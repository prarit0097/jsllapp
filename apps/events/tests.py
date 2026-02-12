from io import StringIO
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.events.models import Announcement
from apps.events.services import high_impact_queryset
from apps.events.utils import build_announcement_dedupe_key


class FetchEventsCommandTests(TestCase):
    def test_fetch_events_summary_total_processed(self):
        out = StringIO()
        with patch('apps.events.management.commands.fetch_events.fetch_news_rss') as mock_news, \
                patch('apps.events.management.commands.fetch_events.fetch_announcements_nse') as mock_ann:
            mock_news.return_value = (0, '')
            mock_ann.return_value = {
                'parsed_count': 2,
                'saved_count': 0,
                'updated_count': 2,
                'skipped_duplicates': 0,
                'parse_errors': 0,
                'errors': [],
            }
            call_command('fetch_events', stdout=out)

        output = out.getvalue()
        self.assertIn('total_processed=2', output)
        self.assertIn('created=0', output)
        self.assertIn('updated=2', output)

    def test_fetch_events_reclassify_flag_calls(self):
        out = StringIO()
        with patch('apps.events.management.commands.fetch_events.fetch_news_rss') as mock_news, \
                patch('apps.events.management.commands.fetch_events.fetch_announcements_nse') as mock_ann, \
                patch('apps.events.management.commands.fetch_events.call_command') as mock_call:
            mock_news.return_value = (0, '')
            mock_ann.return_value = {
                'parsed_count': 1,
                'saved_count': 0,
                'updated_count': 1,
                'skipped_duplicates': 0,
                'parse_errors': 0,
                'errors': [],
            }
            call_command('fetch_events', '--reclassify', stdout=out)

        mock_call.assert_called_with('reclassify_announcements')


class HighImpactQuerysetTests(TestCase):
    def _create_announcement(self, headline, published_at, impact_score=20, low_priority=False):
        dedupe_key = build_announcement_dedupe_key('JSLL', headline, published_at, '', '')
        return Announcement.objects.create(
            dedupe_key=dedupe_key,
            published_at=published_at,
            headline=headline,
            url='',
            type='results',
            polarity=1,
            impact_score=impact_score,
            low_priority=low_priority,
            dedupe_hash=None,
            tags_json={'tags': []},
        )

    def test_high_impact_rolling_window_boundaries(self):
        fixed_now = timezone.now()
        within = fixed_now - timedelta(days=6, hours=23, minutes=59)
        exact = fixed_now - timedelta(days=7)
        older = fixed_now - timedelta(days=7, minutes=1)

        self._create_announcement('within', within)
        self._create_announcement('exact', exact)
        self._create_announcement('older', older)

        with patch('apps.events.services.timezone.now', return_value=fixed_now):
            qs = high_impact_queryset(days=7)

        headlines = set(qs.values_list('headline', flat=True))
        self.assertIn('within', headlines)
        self.assertIn('exact', headlines)
        self.assertNotIn('older', headlines)

    def test_reclassify_prints_helper_counts(self):
        now = timezone.now()
        self._create_announcement('Outcome of Board Meeting - Unaudited Financial Results', now)
        out = StringIO()
        call_command('reclassify_announcements', stdout=out)
        output = out.getvalue()
        self.assertIn('High impact (7d, rolling_168h): 1', output)
        self.assertIn('High impact (7d, calendar_days):', output)
