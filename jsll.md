# JSLL Project Deep Analysis

## 1. Executive Summary

JSLL Decision Intelligence ek Django + Django REST Framework + Celery based backend service hai jo ek hi stock/instrument `JSLL.NS` ko deeply monitor karta hai. Yeh system minute-level market candles, RSS news, aur NSE corporate announcements ko collect karta hai, unko clean aur dedupe karta hai, phir un data points se features, heuristic scores, aur short-horizon price predictions generate karta hai.

Is repo ka main output do forms mein milta hai:

- Human-readable dashboard at `/`
- Machine-readable JSON APIs under `/api/v1/...` aur `/api/predictions/latest`

### Important inference

Code aur existing docs ko dekhkar strong inference yeh hai ki yeh project kisi general stock screener ya brokerage platform ke liye nahi bana, balki ek single-stock decision-support tool ke roop mein bana hai. Iska focus `Jeena Sikho Lifecare` / `JSLL.NS` par hai. Repo ke andar kisi trading execution, auth, portfolio management, ya multi-user workflow ka implementation nahi hai.

## 2. App Kya Karta Hai

Yeh app:

- `JSLL.NS` ke 1-minute OHLCV candles collect karta hai
- Price provider failures ke liye dual-source fallback use karta hai
- Missing candles fill karta hai aur price outliers reject karta hai
- RSS news aur NSE announcements fetch karta hai
- News ka simple sentiment score nikalta hai
- Announcements ko taxonomy ke through classify karta hai
- High-impact vs low-priority events ko separate karta hai
- Price + volume + news + announcement + volatility based signal scores banata hai
- Multiple horizons (`1h`, `3h`, `5h`, `1d`) ke predictions generate karta hai
- Latest system health, data freshness, scores aur predictions API aur dashboard par expose karta hai

## 3. Yeh App Kyon Needed Hai

Code ke basis par is project ki likely need yeh lagti hai:

- Single stock ko manually monitor karna noisy aur repetitive hota hai
- Price data akela enough nahi hota; news aur corporate announcements ka context bhi chahiye hota hai
- Data freshness important hai, khas kar minute-level monitoring mein
- Raw data ko action-oriented score/prediction mein convert karna operationally useful hota hai
- Operator ko ek jagah par live-ish dashboard aur APIs dono chahiye hote hain

## 4. High-Level Architecture

End-to-end flow:

1. `manage.py` Django ko `config.settings.dev` ke saath start karta hai.
2. `config/celery.py` Redis-backed Celery app aur beat schedule define karta hai.
3. Market tasks `yfinance` based providers se 1m candle data fetch karte hain.
4. Reconciliation + data quality cleaning ke baad candles `Ohlc1m` table mein save hote hain.
5. Event tasks RSS feeds aur NSE announcements fetch karte hain.
6. Events classify/dedupe hoke `NewsItem` aur `Announcement` tables mein save hote hain.
7. Feature pipeline latest candles aur recent events se `Feature1m` aur `SignalScore` banati hai.
8. Prediction pipeline historical candles/events/news se dataframe build karke ML model train karti hai aur `PricePrediction` rows save karti hai.
9. Dashboard aur APIs in tables se latest state serve karte hain.

Simple flow diagram:

```text
External Data
  -> yfinance history/download
  -> Google News RSS
  -> NSE corporate announcements

Background Jobs
  -> market ingest
  -> events fetch
  -> feature scoring
  -> prediction generation

Database
  -> Ohlc1m
  -> IngestRun
  -> NewsItem
  -> Announcement
  -> EventsFetchRun
  -> Feature1m
  -> SignalScore
  -> PricePredictionRun
  -> PricePrediction

Presentation
  -> Django template dashboard
  -> DRF JSON APIs
  -> OpenAPI / Swagger / ReDoc
```

## 5. Tech Stack

- Python 3.10.11 verified in local `.venv`
- Django 5.2.x
- Django REST Framework
- drf-spectacular for schema/docs
- Celery 5.6.x
- Redis as broker/backend
- yfinance as market data source
- pandas + numpy for dataframe/feature engineering
- scikit-learn optional for Gradient Boosting model
- SQLite fallback for local dev
- PostgreSQL supported through `DATABASE_URL`
- feedparser + BeautifulSoup + requests for event ingestion

## 6. Current Repo State Observations

- Existing `README.md`, `docs/architecture.md`, aur `docs/api.md` app ko "Phase 0" bolte hain, lekin actual code kaafi aage badh chuka hai.
- Repo mein local runtime artifacts bhi present hain, jaise `db.sqlite3`, `celerybeat-schedule.*`, aur `logs/`.
- `.gitignore` in artifacts ko ignore karta hai, isliye unka repo mein present hona indicate karta hai ki local workspace active use mein raha hai.
- `.env.example` useful hai, lekin code ke saare optional knobs usme listed nahi hain; example ke bahar bhi env-supported behavior present hai.
- User-provided operational context ke mutabik project Hostinger VPS par live hai, lekin deployment automation/config files repo ke andar tracked nahi hain.

## 7. Repo Structure Overview

High-value directories:

- `config/`: Django project config, settings, URLs, ASGI/WSGI, Celery
- `apps/api/`: API layer aur dashboard view
- `apps/market/`: market data ingestion
- `apps/events/`: RSS + NSE announcement ingestion and classification
- `apps/features/`: feature engineering and score generation
- `apps/predictions/`: ML-style prediction generation and backtesting
- `apps/financials/`: placeholder
- `apps/ml/`: placeholder
- `apps/tournament/`: placeholder
- `templates/`: dashboard HTML + JS
- `scripts/`: local dev runner
- `docs/`: older docs

## 8. Startup Sequence

### `manage.py`

- Default settings module `config.settings.dev` set karta hai.
- Standard Django CLI entrypoint hai.

### `config/settings/__init__.py`

- Directly `dev.py` import karta hai.
- Is repo mein effective default environment dev hi hai.

### `config/settings/dev.py`

- `base.py` import karta hai.
- `DEBUG` ko default `true` banata hai jab env override na ho.

### `config/settings/base.py`

Yeh repo ka real control center hai:

- `.env` load karta hai
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` read karta hai
- `JSLL_TICKER`, `JSLL_MARKET_TZ`, `JSLL_PRICE_DELAY_SEC` define karta hai
- Installed apps list karta hai
- Templates path configure karta hai
- DB ko `DATABASE_URL` ke through Postgres ya fallback SQLite par set karta hai
- DRF ko JSON-only renderer par set karta hai
- drf-spectacular schema metadata define karta hai
- Celery broker/result backend ke liye `REDIS_URL` use karta hai
- Logging config set karta hai

### `config/__init__.py`

- Celery app expose karta hai as `celery_app`.

### `config/celery.py`

- Celery app initialize karta hai
- Django settings se `CELERY_` namespace config load karta hai
- Beat schedule define karta hai:
  - market ingest every 60 sec
  - events fetch open market every 600 sec
  - events fetch closed market every 1800 sec
  - score compute every 60 sec
  - prediction every 300 sec

### `config/urls.py`

- `/` ko dashboard view se map karta hai
- `/admin/` admin panel
- `/api/v1/` app APIs
- `/api/predictions/latest` shortcut route
- `/api/schema/`, `/api/docs/`, `/api/redoc/` docs
- Same docs endpoints ka `/api/v1/schema/`, `/api/v1/docs/`, `/api/v1/redoc/` variant bhi `apps.api.urls` ke through available hai

### `config/asgi.py` and `config/wsgi.py`

- Standard deployment entrypoints
- Dono `config.settings.dev` use karte hain

## 9. Database Model Summary

| Model | Purpose | Key Fields |
|---|---|---|
| `Ohlc1m` | 1-minute market candles | `ts`, `open`, `high`, `low`, `close`, `volume`, `source` |
| `IngestRun` | Market ingest audit trail | provider names, success flags, fetched/saved counts, notes |
| `NewsItem` | RSS news storage | `published_at`, `source`, `title`, `url`, `summary`, `sentiment` |
| `Announcement` | NSE announcement storage | `headline`, `published_at`, `type`, `impact_score`, `low_priority`, `dedupe_key` |
| `EventsFetchRun` | Events pipeline audit trail | `news_ok`, `announcements_ok`, counts, notes |
| `Feature1m` | Raw engineered features per minute | `ts`, `feature_json` |
| `SignalScore` | Business-facing score snapshot | component scores + `overall_score` + `explain_json` |
| `PricePredictionRun` | Backtest / run metadata | train/test dates, status, metrics |
| `PricePrediction` | Latest horizon predictions | `ts`, `horizon_min`, returns, price, model, confidence |

## 10. App-by-App Deep Dive

## 10.1 `apps/api`

Purpose:

- External JSON API expose karna
- Dashboard ko server-rendered landing page dena
- Pipeline state ko serialize karke frontend polling ke liye ready karna

Important files:

- `views.py`: actual HTTP behavior
- `urls.py`: API route map
- `serializers.py`: response schemas
- `tests.py`: health, meta, quote, OHLC, pipeline endpoint tests

Key behaviors:

- `dashboard()` latest candles, last ingest run, event counts, score freshness, and pipeline state template mein bhejta hai
- `HealthView` returns `{"status":"ok"}`
- `MetaView` app/version deta hai
- `Ohlc1mView` recent candles deta hai with `limit`
- `LatestQuoteView` price freshness aur delay state deta hai
- `PipelineStatusView` data freshness + completeness + market state deta hai
- `NewsView` recent RSS items deta hai
- `AnnouncementsView` recent announcements deta hai
- `EventsSummaryView` news + announcement aggregate metrics deta hai
- `ScoresLatestView` latest category scores deta hai
- `PredictionsLatestView` latest multi-horizon predictions aur latest backtest metrics deta hai

Important internal helpers:

- `_pipeline_status()` dashboard/API health logic ka center hai
- `_format_market_time()` UTC timestamps ko market timezone string mein convert karta hai
- `_extract_delay_reason()` ingest notes se delay hints nikalta hai
- `PredictionsLatestView` teen URLs par mounted hai: `/api/v1/jsll/predictions/latest`, `/api/v1/predictions/latest`, aur `/api/predictions/latest`

## 10.2 `apps/market`

Purpose:

- Market price ingestion
- Provider reconciliation
- Data quality enforcement
- Celery ingest scheduling

Core files:

- `models.py`
- `services.py`
- `tasks.py`
- `reconcile.py`
- `data_quality.py`
- `market_time.py`
- `providers/*`
- `management/commands/ingest_1m.py`
- `management/commands/celery_healthcheck.py`

### `models.py`

- `Ohlc1m`: primary market timeseries table
- `IngestRun`: ingestion run metadata

### `services.py`

Important functions:

- `_fetch_with_optional_window()`: provider signature flexibility support
- `ingest_1m_candles(provider)`: single-provider ingest path
- `ingest_1m_candles_multi(primary_provider, fallback_provider)`: main production path

Main logic:

- Latest DB candle detect karta hai
- Provider se recent batch fetch karta hai
- Existing latest timestamp se duplicate overlap filter karta hai
- `DataQualityEngine` se clean karta hai
- `bulk_create(ignore_conflicts=True)` se candles save karta hai
- `IngestRun` mein audit metadata store karta hai

### `reconcile.py`

Dual-source merge strategy:

- Same timestamp par primary-only ho to primary use
- Fallback-only ho to fallback use
- Dono present hon to price difference compare hota hai
- Agar close price diff `> 2%` ho to higher-volume source choose hota hai
- Otherwise primary preferred hai

### `data_quality.py`

`DataQualityEngine` 3 major checks karta hai:

- Missing candles gap-fill using previous close and zero volume
- Outlier rejection via max jump percentage
- Negative volume normalization to zero

Current default:

- `max_jump_pct = 0.15`

### `market_time.py`

Market session helpers:

- Open: `09:15`
- Close: `15:30`
- Weekend closed
- Near close window: `15:20` to `15:30`
- `compute_thresholds()` freshness/completeness thresholds return karta hai
- Pipeline status now adaptive freshness threshold use karta hai, jisse near-close window mein delay tolerance relax hoti hai

### `tasks.py`

- `ingest_1m_task()` Celery shared task hai
- Market closed ho to skip karta hai
- `YFinanceHistoryProvider` primary aur `YFinanceDownloadProvider` fallback use karta hai
- Logging detail mein summary print karti hai

### Providers

- `base.py`: abstract provider interface
- `yfinance_provider.py`: `Ticker().history()` based primary provider
- `yfinance_download_provider.py`: `yf.download()` based fallback provider
- `stooq_provider.py`: alternate CSV-based provider, current pipeline mein wired nahi
- `mock_provider.py`: tests ke liye synthetic candles
- `errors.py`: `ProviderError`

### Commands

- `ingest_1m`: manual ingest run
- `celery_healthcheck`: broker/worker/data freshness check

## 10.3 `apps/events`

Purpose:

- JSLL-related news aur announcements collect karna
- Text classification aur dedupe
- Event significance quantify karna

Core files:

- `models.py`
- `services.py`
- `tasks.py`
- `rss.py`
- `nse.py`
- `sentiment.py`
- `taxonomy.py`
- `utils.py`
- `management/commands/*`

### `models.py`

- `NewsItem`: RSS items with sentiment and tags
- `Announcement`: classified NSE disclosure record
- `EventsFetchRun`: run status table

### `rss.py`

News ingestion logic:

- Default keywords:
  - `JSLL`
  - `Jeena Sikho Lifecare`
  - `Jeena Sikho`
- Google News RSS search URLs build hoti hain
- `EVENTS_RSS_URLS` env se custom feeds add ho sakti hain
- `feedparser` entries ko normalized dict mein convert kiya jata hai

### `sentiment.py`

Simple keyword lexicon sentiment:

- Positive word set
- Negative word set
- Score range `-1.0` to `1.0`
- Pure heuristic implementation, ML model nahi

### `taxonomy.py`

Announcement classification rules:

- `results`
- `board_meeting`
- `dividend`
- `bonus`
- `split`
- `fundraise`
- `legal`
- `insider`
- `compliance`
- fallback `other`

Saath mein:

- `polarity`
- `impact_score`
- `low_priority`
- `tags`

Business meaning:

- High-impact disclosures score ko boost karte hain
- Compliance/noise items low-priority mark hote hain

### `utils.py`

Deduplication helpers:

- text normalize
- URL normalize
- timestamp ko IST minute level par floor
- SHA1-based `dedupe_key` build
- softer dedupe for same minute + same doc URL

### `nse.py`

NSE scraping/fetching logic:

- session initialize with browser-like headers
- JSON corporate announcements endpoint use
- fallback HTML scraping if JSON empty
- `published_text` multiple formats parse karke UTC datetime banata hai
- output list headline + timestamp + URL + source_id ke saath return hoti hai

### `services.py`

Important functions:

- `high_impact_queryset()`: announcement filtering helper
- `fetch_news_rss()`: RSS fetch + sentiment + tags + save
- `fetch_announcements_nse()`: fetch + parse + classify + dedupe + update/create
- `create_announcement_from_text()`: utility creator

Key behavior:

- Announcement dedupe `dedupe_key` se hota hai
- `update_or_create()` use hota hai, isliye repeated fetch idempotent hai
- Parse errors sample mode mein print ho sakte hain

### `tasks.py`

- `fetch_events_task(schedule_type='open'|'closed')`
- Market state ke hisab se run/skip decide hota hai
- RSS aur NSE dono run hote hain
- Results `EventsFetchRun` mein saved hote hain

### Commands

- `fetch_events`: manual full fetch
- `fetch_events --reclassify`: fetch ke baad reclassification
- `reclassify_announcements`: existing rows ko re-score aur dedupe-key refresh
- `dedupe_announcements`: duplicates delete
- `backfill_dedupe_keys`: historical rows ko new dedupe regime mein migrate

## 10.4 `apps/features`

Purpose:

- Raw data ko structured signals mein convert karna
- Lightweight decision score produce karna

Core files:

- `models.py`
- `compute.py`
- `scoring.py`
- `services.py`
- `tasks.py`
- `management/commands/compute_scores.py`

### `compute.py`

Feature engineering source of truth:

- Recent 240 candles pull karta hai
- Returns compute karta hai: `1m`, `5m`, `15m`
- RSI 14 using Wilder smoothing
- ATR 14
- `atr_pct` as ATR divided by close price
- candle body and range percentage
- volume z-score over `20` and `60`
- session VWAP distance (`vwap_dist`) compute karta hai
- realized volatility
- announcement counts/sums in `24h` and `7d`
- result flag in `7d`
- time since last high impact announcement
- news count and average sentiment in `24h`
- volatility-based regime label

Implementation nuances:

- RSI ke liye full available close history use hoti hai so that Wilder warm-up better ho
- VWAP current IST trading session ke candles se banta hai
- Zero-volume synthetic fill candles VWAP calculation mein include nahi hote

Leakage prevention:

- Sirf `published_at <= ts_floor` events include karta hai
- Future announcements/news current feature row ko leak nahi karte

### `scoring.py`

Raw features ko `0-100` range scores mein map karta hai:

- `price_action_score`
- `volume_score`
- `news_score`
- `announcements_score`
- `regime_score`
- `overall_score`

Weighting:

- Price action: 30%
- Volume: 20%
- Announcements: 20%
- News: 15%
- Regime: 15%

Output mein `explain_json` bhi aata hai jisme:

- key features
- top reasons
- category-specific reasons for `price_action`, `volume`, `announcements`, `news`, `regime`

Scoring detail:

- Price action ab RSI + 15m momentum context ke saath explain hota hai
- Regime explanation mein meaningful VWAP displacement bhi include ho sakta hai
- Dashboard is `category_reasons` structure ko directly use karta hai

### `services.py`

- `compute_and_store(ts)`: feature and score snapshot create/update
- `compute_latest_missing()`: latest candle ke liye missing score compute karta hai

### `tasks.py`

- `compute_scores_task()` sirf market open state mein run hota hai
- Latest missing score compute karta hai

### Command

- `compute_scores`: manual score generation

## 10.5 `apps/predictions`

Purpose:

- Historical candles + event context ka use karke latest multi-horizon predictions generate karna
- Basic walk-forward backtest store karna

Core files:

- `models.py`
- `services.py`
- `tasks.py`
- `management/commands/prediction_run_once.py`

### `models.py`

- `PricePredictionRun`: backtest/run metadata
- `PricePrediction`: per-horizon latest prediction row

### `services.py`

Yeh repo ka most advanced module hai.

Feature set:

- Returns: `r1`, `r5`, `r15`, `r60`, `r120`
- Rolling volatility
- Momentum windows
- Range mean windows
- Volume z-score windows
- Technical indicators: RSI, ATR%, MACD histogram, Bollinger `%B`
- Intraday context: session VWAP distance and session-open-to-now return
- Event window counts/sums for `2h`, `24h`, `7d`
- Results flags
- News counts and sentiment windows

Prediction horizons:

- `1h` = 60 min
- `3h` = 180 min
- `5h` = 300 min
- `1d` = next trading day close

Model strategy:

- Agar `sklearn` available ho to regularized `GradientBoostingRegressor`
- Warna closed-form ridge regression fallback
- Dono model paths v2 variants use kar rahe hain with held-out residual estimation

Training behavior:

- Latest prediction ke liye roughly last 180 days ka dataframe build hota hai
- Labels future returns se bante hain
- Har horizon ke liye separate model train hota hai
- Latest row par predict karke `PricePrediction` upsert hota hai
- Synthetic gap-fill candles (`volume = 0`) training sample ke roop mein exclude kiye jate hain
- Model training ke liye per-horizon minimum sample threshold higher ki gayi hai
- Confidence horizon-specific out-of-sample residual baselines se derive hoti hai

Backtesting:

- `run_backtest_and_store()` rolling train/test window style evaluation karta hai
- Metrics:
  - MAE
  - directional accuracy
  - sample count
- Test window boundaries bhi `PricePredictionRun` mein save hoti hain

### `tasks.py`

- `prediction_task()` har 5 minute market open condition mein run hota hai
- Latest predictions generate karta hai

### Command

- `prediction_run_once`
- `prediction_run_once --backtest`

## 10.6 `apps/financials`

Status:

- Installed hai
- Model/view/test/admin/app shell scaffold level par hai
- Abhi real financial statement ingestion or analytics implemented nahi hai
- Migrations bhi nahi hain

## 10.7 `apps/ml`

Status:

- Installed hai
- Placeholder only
- Real model registry, training artifact storage, experiment tracking yahan abhi nahi hai

## 10.8 `apps/tournament`

Status:

- Installed hai
- Placeholder only
- Shayad future model comparison/tournament ke liye intended ho, lekin current code mein empty scaffold hai

## 11. Dashboard Behavior

`templates/dashboard.html` repo ka only frontend hai.

Implementation detail:

- CSS aur JavaScript dono inline same template mein embedded hain; separate static asset bundle abhi nahi hai

Server-rendered sections:

- ticker
- last price placeholder
- last candle time
- pipeline status
- last ingest run
- predictions cards
- backtest table
- signal scores
- event summary
- recent candles table

Frontend JS polling:

- Quote refresh every 3 sec
- Pipeline/events/scores/predictions/OHLC refresh every 15 sec

Dashboard APIs used:

- `/api/v1/jsll/quote/latest`
- `/api/v1/jsll/pipeline/status`
- `/api/v1/jsll/events/summary`
- `/api/v1/jsll/scores/latest`
- `/api/predictions/latest`
- `/api/v1/jsll/ohlc/1m?limit=20`

UX purpose:

- Operator ko raw DB query ki zarurat na pade
- Live-ish operational console mil jaye

Extra runtime details:

- Header note ab explicitly live automatic monitoring batata hai
- Dashboard prediction area explicitly `"Experimental. Not financial advice."` show karta hai
- Score bars aur event badges client-side JS se update hote hain
- Latest price widget delayed/live state ko `live-dot` aur `LIVE/DELAYED` pill se indicate karta hai
- Score card ab generic top reasons ke bajay category-specific reason strings render karta hai

## 12. API Catalog

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | HTML dashboard |
| GET | `/admin/` | Django admin |
| GET | `/api/v1/health` | basic health |
| GET | `/api/v1/meta` | app metadata |
| GET | `/api/v1/jsll/ohlc/1m` | recent candles |
| GET | `/api/v1/jsll/quote/latest` | latest quote + freshness |
| GET | `/api/v1/jsll/pipeline/status` | pipeline health |
| GET | `/api/v1/jsll/news` | recent news |
| GET | `/api/v1/jsll/announcements` | recent announcements |
| GET | `/api/v1/jsll/events/summary` | event aggregates |
| GET | `/api/v1/jsll/scores/latest` | latest signal scores |
| GET | `/api/v1/jsll/predictions/latest` | latest predictions |
| GET | `/api/v1/predictions/latest` | prediction shortcut inside v1 prefix |
| GET | `/api/predictions/latest` | same prediction shortcut |
| GET | `/api/v1/schema/` | OpenAPI schema under v1 prefix |
| GET | `/api/v1/docs/` | Swagger UI under v1 prefix |
| GET | `/api/v1/redoc/` | ReDoc under v1 prefix |
| GET | `/api/schema/` | OpenAPI schema |
| GET | `/api/docs/` | Swagger UI |
| GET | `/api/redoc/` | ReDoc |

Routing nuance:

- Most JSON endpoints slashless hain, jabki schema/docs endpoints trailing slash ke saath defined hain
- Predictions endpoint intentionally multiple URLs par exposed hai for dashboard compatibility and convenience

## 13. Celery Schedule

Defined in `config/celery.py`:

| Task | Schedule | Notes |
|---|---|---|
| `apps.market.tasks.ingest_1m_task` | every 60 sec | market-open only |
| `apps.events.tasks.fetch_events_task('open')` | every 600 sec | runs when market open |
| `apps.events.tasks.fetch_events_task('closed')` | every 1800 sec | runs when market closed |
| `apps.features.tasks.compute_scores_task` | every 60 sec | market-open only |
| `apps.predictions.tasks.prediction_task` | every 300 sec | market-open only |

## 14. Environment Variables

From `.env.example` and settings:

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Django secret |
| `DEBUG` | debug mode |
| `ALLOWED_HOSTS` | allowed hostnames |
| `DATABASE_URL` | Postgres DSN; empty means SQLite fallback |
| `REDIS_URL` | Celery broker/backend |
| `TIMEZONE` | Django timezone |
| `JSLL_TICKER` | tracked ticker, default `JSLL.NS` |
| `JSLL_MARKET_TZ` | market timezone, default `Asia/Kolkata` |
| `JSLL_PRICE_DELAY_SEC` | freshness threshold |
| `EVENTS_RSS_URLS` | optional comma-separated RSS feed override/extension list |
| `LOG_LEVEL` | root logger level |
| `DJANGO_LOG_LEVEL` | Django logger level |
| `APP_LOG_LEVEL` | app logger level |

Related settings details:

- `USE_TZ = True`
- `STATIC_URL = 'static/'`
- DRF renderer JSON-only hai, isliye browsable API enabled nahi hai
- Logging default console-only hai with `root`, `django`, aur `apps` loggers

## 15. Commands to Run the Project

## 15.1 First-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
```

## 15.2 Run only Django

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

## 15.3 One-command dev run

```powershell
.\scripts\run_dev.ps1
```

Yeh script:

- Redis port 6379 check karta hai
- Redis service ya `redis-server` launch karne ki koshish karta hai
- Celery worker `-P solo` ke saath start karta hai
- Celery beat start karta hai
- Django `runserver` launch karta hai
- Worker aur beat logs `logs/celery-worker.out.log`, `logs/celery-worker.err.log`, `logs/celery-beat.out.log`, `logs/celery-beat.err.log` mein redirect hote hain
- Script migrations auto-run nahi karta; DB prep separately karni hoti hai

## 15.4 Manual Celery run

```powershell
.\.venv\Scripts\celery -A config worker -l info -P solo
.\.venv\Scripts\celery -A config beat -l info
```

## 15.5 Operational commands

```powershell
.\.venv\Scripts\python.exe manage.py ingest_1m
.\.venv\Scripts\python.exe manage.py fetch_events
.\.venv\Scripts\python.exe manage.py fetch_events --reclassify
.\.venv\Scripts\python.exe manage.py reclassify_announcements
.\.venv\Scripts\python.exe manage.py dedupe_announcements
.\.venv\Scripts\python.exe manage.py backfill_dedupe_keys
.\.venv\Scripts\python.exe manage.py compute_scores
.\.venv\Scripts\python.exe manage.py prediction_run_once
.\.venv\Scripts\python.exe manage.py prediction_run_once --backtest
.\.venv\Scripts\python.exe manage.py celery_healthcheck
```

## 15.6 QA / debugging commands

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py shell
```

## 16. Verification I Actually Ran

Local workspace mein maine yeh commands run kiye:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py test
```

Observed results:

- Python version: `3.10.11`
- `manage.py check`: no issues
- `manage.py showmigrations`: `events`, `features`, `market`, `predictions` migrations applied; `api`, `financials`, `ml`, `tournament` have no migrations
- `manage.py test`: `54` tests passed

## 17. Migration History

### `apps/market/migrations`

- `0001_initial.py`: `Ohlc1m` table
- `0002_ingestrun.py`: `IngestRun` table

### `apps/events/migrations`

This app ka schema evolution sabse interesting hai:

- `0001_initial.py`: `Announcement`, `EventsFetchRun`, `NewsItem`
- `0002_announcement_uniq_announcement_headline_time.py`: initial dedupe by `(headline, published_at)`
- `0003_announcement_dedupe_hash_announcement_low_priority.py`: `dedupe_hash` and `low_priority`
- `0004_announcement_uniq_announcement_dedupe_hash.py`: `dedupe_hash` unique constraint
- `0005_announcement_dedupe_key.py`: stronger `dedupe_key`
- `0006_remove_dedupe_hash_constraint.py`: hash uniqueness removed
- `0007_drop_headline_published_unique.py`: old headline/time uniqueness removed

Interpretation:

- Project ne dedupe strategy evolve ki hai from naive uniqueness to more controlled business-key based uniqueness.

### `apps/features/migrations`

- `0001_initial.py`: `Feature1m` and `SignalScore`

### `apps/predictions/migrations`

- `0001_initial.py`: `PricePredictionRun` and `PricePrediction`

### Apps with no migrations

- `api`
- `financials`
- `ml`
- `tournament`

## 18. Tests Kya Cover Karte Hain

Covered areas:

- health/meta endpoints
- quote freshness logic
- OHLC endpoint
- pipeline status
- market session logic
- taxonomy/classification rules
- announcement dedupe and parse rules
- event summary API
- ingest behavior
- outlier detection
- provider reconciliation
- score range correctness
- leakage prevention for announcements
- prediction label alignment
- next-trading-day target construction
- predictions latest endpoint
- OpenAPI docs endpoints

Practical meaning:

- Core pipelines ke important behaviors test kiye gaye hain
- Placeholder apps ke tests empty hain

## 19. Strengths of the Current Design

- Single-stock focus se complexity controlled hai
- Market ingestion mein primary + fallback provider design hai
- Data quality engine missing data aur outliers dono handle karta hai
- Announcement dedupe logic mature hai
- Feature computation future leakage avoid karta hai
- Dashboard + API dual-consumer design useful hai
- OpenAPI docs built-in hain
- Celery-based automation already wired hai

## 20. Important Gaps, Risks, and Code Observations

Yeh section documentation ka important part hai. Yeh sab observations code reading par based hain:

- `README.md` aur `docs/*` actual implementation se behind hain
- `.env.example` code-supported env surface ka full superset nahi hai
- `financials`, `ml`, aur `tournament` installed hain but functionally unused hain
- Predictions har run mein fresh train hote hain; model persistence ya registry nahi hai
- `PricePredictionRun` backtest ke liye use hota hai, lekin latest prediction generation ke saath tightly linked nahi hai
- `PricePrediction.run` FK current prediction write path mein populate nahi hota
- Live deployment context user ne mention kiya hai, lekin VPS provisioning/release steps repo mein documented nahi hain
- `LatestQuoteView` ab bhi fixed `JSLL_PRICE_DELAY_SEC` threshold use karta hai, jabki pipeline status adaptive near-close threshold use karta hai
- `fetch_news_rss()` count return karta hai created objects list length ke basis par, not actual inserted rows after conflict ignore
- `fetch_events_task()` announcements fetched count aur management command summary mein semantics mismatch hai
- Admin modules mostly empty hain; admin UI curated nahi hai
- Auth, permissions, rate limiting, audit security, and user workflows absent hain
- Multi-ticker design nahi hai; architecture hard-coded `JSLL` centric hai
- External providers (`yfinance`, Google News RSS, NSE endpoints) brittle ho sakte hain

## 21. What This Project Does Not Yet Do

- No user login/auth system
- No order execution or broker integration
- No alerting system
- No websocket/live push
- No persisted trained ML artifacts
- No robust feature store outside DB JSON snapshots
- No real financial statements ingestion
- No advanced model tournament despite app scaffold
- No production deployment config in repo
- No Hostinger/VPS deployment playbook tracked in repository

## 22. File-by-File Map

Yeh section repo ko file level par summarize karta hai.

### Root

- `README.md`: basic setup/run/test instructions; now partially outdated
- `requirements.txt`: dependency list
- `manage.py`: Django CLI entrypoint
- `jsll.md`: detailed project analysis and internal documentation
- `.env.example`: sample environment variables
- `.gitignore`: Python, venv, SQLite, env, Celery/log ignores
- `scripts/run_dev.ps1`: local all-in-one startup script
- `templates/dashboard.html`: only frontend page

### `docs/`

- `docs/architecture.md`: early-phase architecture note, current implementation se behind
- `docs/api.md`: minimal API note, current API surface se smaller

### `config/`

- `config/__init__.py`: Celery app export
- `config/asgi.py`: ASGI entrypoint
- `config/wsgi.py`: WSGI entrypoint
- `config/urls.py`: URL routing
- `config/celery.py`: Celery app + beat schedule
- `config/settings/__init__.py`: dev settings import
- `config/settings/base.py`: main settings module
- `config/settings/dev.py`: dev override

### `apps/api/`

- `apps/api/apps.py`: app config
- `apps/api/admin.py`: placeholder admin
- `apps/api/models.py`: placeholder models file
- `apps/api/serializers.py`: response serializers
- `apps/api/views.py`: dashboard + all API views
- `apps/api/urls.py`: API routes
- `apps/api/tests.py`: API behavior tests
- `apps/api/migrations/__init__.py`: package marker

### `apps/market/`

- `apps/market/apps.py`: app config
- `apps/market/admin.py`: empty
- `apps/market/models.py`: `Ohlc1m`, `IngestRun`
- `apps/market/services.py`: ingest services
- `apps/market/tasks.py`: Celery ingest task
- `apps/market/reconcile.py`: provider merge policy
- `apps/market/data_quality.py`: gap-fill + outlier handling
- `apps/market/market_time.py`: session logic
- `apps/market/views.py`: placeholder
- `apps/market/tests.py`: market/event/ingest related tests
- `apps/market/providers/base.py`: provider contract
- `apps/market/providers/errors.py`: provider exception
- `apps/market/providers/mock_provider.py`: test provider
- `apps/market/providers/stooq_provider.py`: alternate provider
- `apps/market/providers/yfinance_provider.py`: primary provider
- `apps/market/providers/yfinance_download_provider.py`: fallback provider
- `apps/market/management/commands/ingest_1m.py`: manual ingest
- `apps/market/management/commands/celery_healthcheck.py`: health check
- `apps/market/migrations/0001_initial.py`: market candles table
- `apps/market/migrations/0002_ingestrun.py`: ingest audit table
- `apps/market/migrations/__init__.py`: package marker

### `apps/events/`

- `apps/events/apps.py`: app config
- `apps/events/admin.py`: empty
- `apps/events/models.py`: `NewsItem`, `Announcement`, `EventsFetchRun`
- `apps/events/services.py`: fetch + classify + save
- `apps/events/tasks.py`: Celery event fetch task
- `apps/events/rss.py`: RSS URL generation and parsing
- `apps/events/nse.py`: NSE fetch + datetime parsing
- `apps/events/sentiment.py`: keyword sentiment
- `apps/events/taxonomy.py`: event classification logic
- `apps/events/utils.py`: dedupe key helpers
- `apps/events/views.py`: placeholder
- `apps/events/tests.py`: event command/queryset tests
- `apps/events/management/commands/fetch_events.py`: manual fetch
- `apps/events/management/commands/reclassify_announcements.py`: reclassification command
- `apps/events/management/commands/dedupe_announcements.py`: duplicate cleanup
- `apps/events/management/commands/backfill_dedupe_keys.py`: dedupe-key backfill
- `apps/events/migrations/0001_initial.py`: base event tables
- `apps/events/migrations/0002_announcement_uniq_announcement_headline_time.py`: old uniqueness strategy
- `apps/events/migrations/0003_announcement_dedupe_hash_announcement_low_priority.py`: low priority + hash
- `apps/events/migrations/0004_announcement_uniq_announcement_dedupe_hash.py`: hash uniqueness
- `apps/events/migrations/0005_announcement_dedupe_key.py`: new dedupe key
- `apps/events/migrations/0006_remove_dedupe_hash_constraint.py`: hash constraint removed
- `apps/events/migrations/0007_drop_headline_published_unique.py`: old uniqueness removed
- `apps/events/migrations/__init__.py`: package marker

### `apps/features/`

- `apps/features/apps.py`: app config
- `apps/features/admin.py`: empty
- `apps/features/models.py`: `Feature1m`, `SignalScore`
- `apps/features/compute.py`: feature engineering with Wilder RSI, ATR%, session VWAP and event/news aggregation
- `apps/features/scoring.py`: feature-to-score mapping plus category-specific explanations
- `apps/features/services.py`: compute/store orchestration
- `apps/features/tasks.py`: Celery score task
- `apps/features/views.py`: placeholder
- `apps/features/tests.py`: score + feature tests
- `apps/features/management/commands/compute_scores.py`: manual score compute
- `apps/features/migrations/0001_initial.py`: feature/score tables
- `apps/features/migrations/__init__.py`: package marker

### `apps/predictions/`

- `apps/predictions/apps.py`: app config
- `apps/predictions/models.py`: prediction tables
- `apps/predictions/services.py`: enriched feature dataframe, model train, predict, confidence estimation, backtest
- `apps/predictions/tasks.py`: Celery prediction task
- `apps/predictions/tests.py`: prediction feature/label/API tests
- `apps/predictions/management/commands/prediction_run_once.py`: manual prediction/backtest
- `apps/predictions/management/commands/__init__.py`: package marker
- `apps/predictions/migrations/0001_initial.py`: prediction schema
- `apps/predictions/migrations/__init__.py`: package marker

### `apps/financials/`

- `apps/financials/apps.py`: app config
- `apps/financials/admin.py`: placeholder
- `apps/financials/models.py`: placeholder
- `apps/financials/views.py`: placeholder
- `apps/financials/tests.py`: placeholder
- `apps/financials/migrations/__init__.py`: package marker

### `apps/ml/`

- `apps/ml/apps.py`: app config
- `apps/ml/admin.py`: placeholder
- `apps/ml/models.py`: placeholder
- `apps/ml/views.py`: placeholder
- `apps/ml/tests.py`: placeholder
- `apps/ml/migrations/__init__.py`: package marker

### `apps/tournament/`

- `apps/tournament/apps.py`: app config
- `apps/tournament/admin.py`: placeholder
- `apps/tournament/models.py`: placeholder
- `apps/tournament/views.py`: placeholder
- `apps/tournament/tests.py`: placeholder
- `apps/tournament/migrations/__init__.py`: package marker

### Package markers and empty initializers

- `apps/__init__.py` empty package marker hai
- Most `__init__.py` files under `management/`, `management/commands/`, and `migrations/` sirf package structure maintain karte hain; business logic nahi rakhte

## 23. Bottom Line

Current state mein yeh repo ek focused single-stock analytics backend hai jo:

- data ingest karta hai
- data clean aur dedupe karta hai
- feature and score layers build karta hai
- lightweight prediction pipeline chalata hai
- dashboard + APIs expose karta hai

Is project ki strongest value operational visibility aur single-stock intelligence hai. Iski weakest side unfinished placeholder apps, outdated docs, aur kuch implementation inconsistencies hain. Documentation ke hisab se yeh repo "Phase 0 skeleton" se kaafi aage hai aur ab ise "single-ticker decision-support platform with scheduled ingestion, scoring, and prediction" kehna zyada accurate hoga.
