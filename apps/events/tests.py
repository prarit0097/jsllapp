from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase


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
