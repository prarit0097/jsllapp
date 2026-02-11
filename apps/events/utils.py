import hashlib
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def _normalize(text):
    return ' '.join((text or '').lower().split())


def _normalize_url(url):
    if not url:
        return ''
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path.rstrip('/')
        return _normalize(urlunsplit((scheme, netloc, path, '', '')))
    except Exception:
        return _normalize(url)


def _floor_to_minute_ist(dt):
    if not dt:
        return None
    local = dt
    try:
        local = timezone.localtime(dt, ZoneInfo('Asia/Kolkata'))
    except Exception:
        try:
            local = dt.astimezone(ZoneInfo('Asia/Kolkata'))
        except Exception:
            local = dt
    return local.replace(second=0, microsecond=0)


def build_announcement_dedupe_key(
    symbol,
    headline,
    published_at,
    doc_url='',
    source_id='',
):
    dt_floor = _floor_to_minute_ist(published_at)
    if not dt_floor:
        return None

    symbol_key = _normalize(symbol) if symbol else _normalize(getattr(settings, 'JSLL_TICKER', 'JSLL'))
    headline_norm = _normalize(headline)
    doc_url_norm = _normalize_url(doc_url)
    source_id_norm = _normalize(source_id)
    dt_key = dt_floor.isoformat()

    key_material = f"{symbol_key}|{dt_key}|{headline_norm}|{doc_url_norm}|{source_id_norm}"
    return hashlib.sha1(key_material.encode('utf-8')).hexdigest()


def build_soft_dedupe_key(symbol, published_at, doc_url):
    dt_floor = _floor_to_minute_ist(published_at)
    if not dt_floor:
        return None

    symbol_key = _normalize(symbol) if symbol else _normalize(getattr(settings, 'JSLL_TICKER', 'JSLL'))
    doc_url_norm = _normalize_url(doc_url)
    if not doc_url_norm:
        return None

    dt_key = dt_floor.isoformat()
    key_material = f"{symbol_key}|{dt_key}|{doc_url_norm}"
    return hashlib.sha1(key_material.encode('utf-8')).hexdigest()
