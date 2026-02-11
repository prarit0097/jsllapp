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
    'events-fetch-every-5m': {
        'task': 'apps.events.tasks.fetch_events_task',
        'schedule': 300.0,
    },
}

app.autodiscover_tasks()