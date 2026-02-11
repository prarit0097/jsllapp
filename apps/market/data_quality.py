from datetime import timedelta


class DataQualityEngine:
    def __init__(self, max_jump_pct=0.15):
        self.max_jump_pct = max_jump_pct

    def fill_missing_candles(self, existing_candles, new_candles):
        if not new_candles:
            return []

        last_ts = None
        last_close = None
        if existing_candles:
            last = existing_candles[-1]
            last_ts = last['ts']
            last_close = last['close']

        filled = []
        for candle in new_candles:
            if last_ts is not None:
                gap = int((candle['ts'] - last_ts).total_seconds() // 60)
                if gap > 1:
                    for step in range(1, gap):
                        ts = last_ts + timedelta(minutes=step)
                        filled.append(
                            {
                                'ts': ts,
                                'open': last_close,
                                'high': last_close,
                                'low': last_close,
                                'close': last_close,
                                'volume': 0.0,
                                'source': 'fill',
                            }
                        )
            filled.append(candle)
            last_ts = candle['ts']
            last_close = candle['close']

        return filled

    def detect_outliers(self, candle, prev_candle):
        if prev_candle is None:
            return False
        prev_close = prev_candle['close']
        if prev_close == 0:
            return False
        jump_pct = abs(candle['close'] - prev_close) / prev_close
        return jump_pct > self.max_jump_pct

    def volume_sanity(self, candle):
        if candle['volume'] < 0:
            candle['volume'] = 0.0
        return candle

    def clean_batch(self, existing_last_candle, new_batch):
        if not new_batch:
            return []

        sorted_batch = sorted(new_batch, key=lambda c: c['ts'])
        cleaned = []

        prev = existing_last_candle
        if prev is not None:
            prev = {
                'ts': prev.ts,
                'open': prev.open,
                'high': prev.high,
                'low': prev.low,
                'close': prev.close,
                'volume': prev.volume,
                'source': prev.source,
            }

        for candle in sorted_batch:
            if prev is not None and candle['ts'] <= prev['ts']:
                continue

            if self.detect_outliers(candle, prev):
                continue

            candle = self.volume_sanity(candle)
            cleaned.append(candle)
            prev = candle

        existing_list = [prev] if existing_last_candle is not None else []
        return self.fill_missing_candles(existing_list, cleaned)