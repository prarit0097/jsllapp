# JSLL Decision Intelligence (Phase 0)

A minimal Django + Django REST Framework service for JSLL analytics and prediction.

## Setup
1. Create and activate a virtual environment.
1. Install dependencies.

```bash
python -m pip install django djangorestframework python-dotenv dj-database-url celery
```

1. Create a `.env` file (optional) based on `.env.example`.

## Run
```bash
python manage.py migrate
python manage.py runserver
```

Health check: `GET /api/v1/health`

## Test
```bash
python manage.py test
```

## Settings
- Default settings module: `config.settings.dev`
- Database uses `DATABASE_URL` (Postgres). If missing, falls back to SQLite for local development.
- Redis settings for Celery are controlled by `REDIS_URL`.