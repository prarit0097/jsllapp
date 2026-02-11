from .data_quality import DataQualityEngine
from .models import Ohlc1m


def ingest_1m_candles(provider):
    batch = provider.fetch_latest_1m()
    last_candle = Ohlc1m.objects.order_by('-ts').first()

    engine = DataQualityEngine()
    cleaned = engine.clean_batch(last_candle, batch)

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