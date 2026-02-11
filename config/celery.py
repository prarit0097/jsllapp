import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.beat_schedule = {
    'ingest-1m-every-minute': {
        'task': 'apps.market.tasks.ingest_1m_task',
        'schedule': 60.0,
    },
    'events-fetch-open': {
        'task': 'apps.events.tasks.fetch_events_task',
        'schedule': 600.0,
        'args': ('open',),
    },
    'events-fetch-closed': {
        'task': 'apps.events.tasks.fetch_events_task',
        'schedule': 1800.0,
        'args': ('closed',),
    },
}

app.autodiscover_tasks()