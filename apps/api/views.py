from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.market.models import IngestRun, Ohlc1m


def _serialize_run(run):
    if run is None:
        return None
    return {
        'id': run.id,
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'provider_primary': run.provider_primary,
        'provider_fallback': run.provider_fallback,
        'primary_ok': run.primary_ok,
        'fallback_ok': run.fallback_ok,
        'candles_fetched_primary': run.candles_fetched_primary,
        'candles_fetched_fallback': run.candles_fetched_fallback,
        'candles_saved': run.candles_saved,
        'missing_filled': run.missing_filled,
        'outliers_rejected': run.outliers_rejected,
        'notes': run.notes,
    }


def _format_market_time(dt):
    if not dt:
        return None
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    local_dt = timezone.localtime(dt, tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')


def dashboard(request):
    latest = Ohlc1m.objects.order_by('-ts').first()
    recent = Ohlc1m.objects.order_by('-ts')[:20]
    last_run = IngestRun.objects.first()

    last_candle_time = latest.ts if latest else None
    last_candle_time_ist = _format_market_time(last_candle_time)
    since = timezone.now() - timedelta(minutes=60)
    candles_last_60m = Ohlc1m.objects.filter(ts__gte=since).count()
    data_ok = bool(last_run and (last_run.primary_ok or last_run.fallback_ok) and candles_last_60m > 0)

    return render(
        request,
        'dashboard.html',
        {
            'latest': latest,
            'recent': recent,
            'last_run': last_run,
            'last_candle_time': last_candle_time,
            'last_candle_time_ist': last_candle_time_ist,
            'candles_last_60m': candles_last_60m,
            'data_ok': data_ok,
            'ticker': settings.JSLL_TICKER,
            'market_tz': settings.JSLL_MARKET_TZ,
        },
    )


class HealthView(APIView):
    def get(self, request):
        return Response({'status': 'ok'})


class MetaView(APIView):
    def get(self, request):
        return Response({'app': 'JSLL Decision Intelligence', 'version': '0.1.0'})


class Ohlc1mView(APIView):
    def get(self, request):
        limit = int(request.query_params.get('limit', 100))
        limit = max(1, min(limit, 1000))
        candles = Ohlc1m.objects.order_by('-ts')[:limit]
        payload = [
            {
                'ts': candle.ts,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close,
                'volume': candle.volume,
                'source': candle.source,
            }
            for candle in candles
        ]
        return Response(payload)


class LatestQuoteView(APIView):
    def get(self, request):
        latest = Ohlc1m.objects.order_by('-ts').first()
        now_server = timezone.now().astimezone(timezone.get_current_timezone())
        seconds_since = None
        if latest:
            seconds_since = int((now_server - latest.ts).total_seconds())
        if latest is None:
            return Response(
                {
                    'last_price': None,
                    'last_candle_time': None,
                    'status': 'no_data',
                    'ticker': settings.JSLL_TICKER,
                    'market_tz': settings.JSLL_MARKET_TZ,
                    'now_server_time': now_server,
                    'seconds_since_last_candle': seconds_since,
                    'last_candle_time_ist': None,
                }
            )
        return Response(
            {
                'last_price': latest.close,
                'last_candle_time': latest.ts,
                'status': 'ok',
                'ticker': settings.JSLL_TICKER,
                'market_tz': settings.JSLL_MARKET_TZ,
                'now_server_time': now_server,
                'seconds_since_last_candle': seconds_since,
                'last_candle_time_ist': _format_market_time(latest.ts),
            }
        )


class PipelineStatusView(APIView):
    def get(self, request):
        last_run = IngestRun.objects.first()
        latest = Ohlc1m.objects.order_by('-ts').first()
        last_candle_time = latest.ts if latest else None
        since = timezone.now() - timedelta(minutes=60)
        candles_last_60m = Ohlc1m.objects.filter(ts__gte=since).count()
        data_ok = bool(last_run and (last_run.primary_ok or last_run.fallback_ok) and candles_last_60m > 0)

        return Response(
            {
                'last_run': _serialize_run(last_run),
                'last_candle_time': last_candle_time,
                'candles_last_60m': candles_last_60m,
                'data_ok': data_ok,
                'ticker': settings.JSLL_TICKER,
                'market_tz': settings.JSLL_MARKET_TZ,
            }
        )