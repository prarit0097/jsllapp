# Architecture (Phase 0)

JSLL Decision Intelligence is a Django + Django REST Framework service that exposes minimal HTTP endpoints and provides a foundation for analytics, prediction, and background processing.

## Components
- Django project: `config`
- API app: `apps/api`
- Domain apps (skeleton): `apps/market`, `apps/events`, `apps/financials`, `apps/features`, `apps/ml`, `apps/tournament`
- Celery: `config/celery.py` with Redis broker configuration

## Settings
- Split settings with a dev entrypoint at `config/settings/dev.py`.
- Environment-based configuration via `.env` (see `.env.example`).
- Database uses `DATABASE_URL` (Postgres). If missing, falls back to SQLite for local development.

## Observability
- Console logging via Django logging configuration in `config/settings/base.py`.

## Next Steps (Phase 1)
- Define models per domain app.
- Add API resources and serializers.
- Add Celery tasks for ETL and prediction jobs.