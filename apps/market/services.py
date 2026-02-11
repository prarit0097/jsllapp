from django.utils import timezone

from .data_quality import DataQualityEngine
from .models import IngestRun, Ohlc1m
from .reconcile import reconcile_batches


def ingest_1m_candles(provider):
    batch = provider.fetch_latest_1m()
    last_candle = Ohlc1m.objects.order_by('-ts').first()

    engine = DataQualityEngine()
    cleaned, _stats = engine.clean_batch(last_candle, batch)

    if not cleaned:
        return 0

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
    return len(objects)


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
    return run