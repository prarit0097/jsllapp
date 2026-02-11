# JSLL Decision Intelligence (Phase 0)

A minimal Django + Django REST Framework service for JSLL analytics and prediction.

## Setup
1. Create and activate a virtual environment.

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

1. Install dependencies.

```bash
python -m pip install -r requirements.txt
```

1. Create a `.env` file (optional) based on `.env.example`.

## Run
### One-command dev (Redis + Celery + Django)
```powershell
.\scripts\run_dev.ps1
```

### Manual
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