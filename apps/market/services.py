from datetime import timedelta

from django.utils import timezone

from .data_quality import DataQualityEngine
from .models import IngestRun, Ohlc1m
from .reconcile import reconcile_batches


def _fetch_with_optional_window(provider, start_ts=None, limit=None):
    if start_ts is None and limit is None:
        return provider.fetch_latest_1m()

    try:
        return provider.fetch_latest_1m(start_ts=start_ts, limit=limit)
    except TypeError:
        pass

    try:
        return provider.fetch_latest_1m(start_ts)
    except TypeError:
        pass

    return provider.fetch_latest_1m()


def ingest_1m_candles(provider):
    last_candle = Ohlc1m.objects.order_by('-ts').first()
    db_latest_ts = last_candle.ts if last_candle else None
    start_ts = None
    limit = None
    if db_latest_ts:
        start_ts = db_latest_ts - timedelta(minutes=3)
        limit = 50

    batch = _fetch_with_optional_window(provider, start_ts=start_ts, limit=limit)
    fetched_count = len(batch)
    fetched_end_ts = max((item['ts'] for item in batch), default=None)

    provider_delay_sec = None
    if fetched_end_ts:
        provider_delay_sec = int((timezone.now() - fetched_end_ts).total_seconds())

    summary = {
        'fetched_count': fetched_count,
        'new_ts_count': 0,
        'already_exists_count': 0,
        'saved': 0,
        'no_new_candles': False,
        'fetched_end_ts': fetched_end_ts,
        'db_latest_ts': db_latest_ts,
        'provider_delay_sec': provider_delay_sec,
        'filtered_by_db_latest': False,
    }

    if db_latest_ts and fetched_end_ts and fetched_end_ts <= db_latest_ts:
        summary['no_new_candles'] = True
        summary['already_exists_count'] = fetched_count
        return summary

    if db_latest_ts:
        filtered = [item for item in batch if item['ts'] > db_latest_ts]
        summary['already_exists_count'] = fetched_count - len(filtered)
        summary['filtered_by_db_latest'] = summary['already_exists_count'] > 0
    else:
        filtered = list(batch)

    if not filtered:
        return summary

    engine = DataQualityEngine()
    cleaned, _stats = engine.clean_batch(last_candle, filtered)

    if not cleaned:
        return summary

    objects = [
        Ohlc1m(
            ts=item['ts'],
            open=item['open'],
            high=item['high'],
            low=item['low'],
            close=item['close'],
            volume=item['volume'],
            source=item.get('source', 'unknown'),
        )
        for item in cleaned
    ]

    Ohlc1m.objects.bulk_create(objects, ignore_conflicts=True)
    summary['saved'] = len(objects)
    summary['new_ts_count'] = len(objects)
    return summary


def ingest_1m_candles_multi(primary_provider, fallback_provider):
    run = IngestRun.objects.create(
        provider_primary=primary_provider.__class__.__name__,
        provider_fallback=fallback_provider.__class__.__name__,
    )

    primary_batch = []
    fallback_batch = []
    notes = []

    try:
        primary_batch = primary_provider.fetch_latest_1m()
        run.primary_ok = True
        run.candles_fetched_primary = len(primary_batch)
    except Exception as exc:
        notes.append(f"primary failed: {exc}")

    try:
        fallback_batch = fallback_provider.fetch_latest_1m()
        run.fallback_ok = True
        run.candles_fetched_fallback = len(fallback_batch)
    except Exception as exc:
        notes.append(f"fallback failed: {exc}")

    merged = reconcile_batches(primary_batch, fallback_batch)
    last_candle = Ohlc1m.objects.order_by('-ts').first()
    db_latest_ts = last_candle.ts if last_candle else None

    fetched_end_ts = max((item['ts'] for item in merged), default=None)
    provider_delay_sec = None
    if fetched_end_ts:
        provider_delay_sec = int((timezone.now() - fetched_end_ts).total_seconds())
        notes.append(f"provider_delay_sec={provider_delay_sec}")
        notes.append(f"fetched_end_ts={fetched_end_ts.isoformat()}")
    if db_latest_ts:
        notes.append(f"db_latest_ts={db_latest_ts.isoformat()}")

    meta = {
        'fetched_end_ts': fetched_end_ts,
        'db_latest_ts': db_latest_ts,
        'provider_delay_sec': provider_delay_sec,
        'no_new_candles': False,
    }

    if fetched_end_ts and db_latest_ts and fetched_end_ts <= db_latest_ts:
        meta['no_new_candles'] = True
        notes.append('no_new_candles')
        run.candles_saved = 0
        run.missing_filled = 0
        run.outliers_rejected = 0
        run.notes = '; '.join(notes)
        run.finished_at = timezone.now()
        run.save()
        return run, meta

    engine = DataQualityEngine()
    cleaned, stats = engine.clean_batch(last_candle, merged)

    if cleaned:
        objects = [
            Ohlc1m(
                ts=item['ts'],
                open=item['open'],
                high=item['high'],
                low=item['low'],
                close=item['close'],
                volume=item['volume'],
                source=item.get('source', 'unknown'),
            )
            for item in cleaned
        ]
        Ohlc1m.objects.bulk_create(objects, ignore_conflicts=True)
        run.candles_saved = len(objects)

    run.missing_filled = stats.get('missing_filled', 0)
    run.outliers_rejected = stats.get('outliers_rejected', 0)
    run.notes = '; '.join(notes)
    run.finished_at = timezone.now()
    run.save()
    return run, meta
