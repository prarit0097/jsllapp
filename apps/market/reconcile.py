from collections import defaultdict


def reconcile_batches(primary_batch, fallback_batch):
    primary_map = {candle['ts']: candle for candle in primary_batch}
    fallback_map = {candle['ts']: candle for candle in fallback_batch}

    all_ts = sorted(set(primary_map.keys()) | set(fallback_map.keys()))
    merged = []

    for ts in all_ts:
        primary = primary_map.get(ts)
        fallback = fallback_map.get(ts)
        if primary and not fallback:
            candle = dict(primary)
            candle['source'] = 'primary'
            merged.append(candle)
            continue
        if fallback and not primary:
            candle = dict(fallback)
            candle['source'] = 'fallback'
            merged.append(candle)
            continue

        if primary and fallback:
            close_primary = primary.get('close', 0)
            close_fallback = fallback.get('close', 0)
            diff_pct = 0
            if close_primary:
                diff_pct = abs(close_primary - close_fallback) / close_primary
            if diff_pct > 0.02:
                vol_primary = primary.get('volume', 0)
                vol_fallback = fallback.get('volume', 0)
                if vol_fallback > vol_primary:
                    candle = dict(fallback)
                    candle['source'] = 'fallback'
                else:
                    candle = dict(primary)
                    candle['source'] = 'primary'
            else:
                candle = dict(primary)
                candle['source'] = 'primary'
            merged.append(candle)

    merged.sort(key=lambda c: c['ts'])
    return merged