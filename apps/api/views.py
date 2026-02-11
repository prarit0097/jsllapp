from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Avg, Sum
from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.serializers import (
    AnnouncementSerializer,
    EventsSummarySerializer,
    HealthResponseSerializer,
    LatestQuoteSerializer,
    MetaResponseSerializer,
    NewsItemSerializer,
    OhlcCandleSerializer,
    PipelineStatusSerializer,
)
from apps.events.models import Announcement, EventsFetchRun, NewsItem
from apps.market.market_time import (
    compute_thresholds,
    is_within_today_session_end,
    market_state,
)
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


def _serialize_events_run(run):
    if run is None:
        return None
    return {
        'id': run.id,
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'news_ok': run.news_ok,
        'announcements_ok': run.announcements_ok,
        'news_fetched': run.news_fetched,
        'announcements_fetched': run.announcements_fetched,
        'notes': run.notes,
    }


def _format_market_time(dt):
    if not dt:
        return None
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    local_dt = timezone.localtime(dt, tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')


def _freshness(latest):
    now_server = timezone.now().astimezone(timezone.get_current_timezone())
    seconds_since = None
    if latest:
        seconds_since = int((now_server - latest.ts).total_seconds())
    return now_server, seconds_since


def _pipeline_status(latest, candles_last_60m):
    tz = ZoneInfo(settings.JSLL_MARKET_TZ)
    now_ist = timezone.now().astimezone(tz)
    state = market_state(now_ist)
    freshness_sec, min_candles_60m = compute_thresholds(now_ist)

    now_server, seconds_since = _freshness(latest)
    freshness_ok = latest is not None and seconds_since is not None and seconds_since <= freshness_sec
    completeness_ok = candles_last_60m >= min_candles_60m

    if state == 'CLOSED':
        status = 'closed' if is_within_today_session_end(latest.ts if latest else None) else 'degraded'
    else:
        status = 'ok' if (freshness_ok and completeness_ok) else 'degraded'

    reason = f"freshness={seconds_since}s, candles_60m={candles_last_60m}"

    return {
        'market_state': state,
        'freshness_ok': freshness_ok,
        'completeness_ok': completeness_ok,
        'status': status,
        'reason': reason,
        'thresholds': {
            'freshness_sec': freshness_sec,
            'min_candles_60m': min_candles_60m,
        },
        'now_server_time': now_server,
        'seconds_since_last_candle': seconds_since,
    }


def _ist_now():
    return timezone.now().astimezone(ZoneInfo(settings.JSLL_MARKET_TZ))


def dashboard(request):
    latest = Ohlc1m.objects.order_by('-ts').first()
    recent = Ohlc1m.objects.order_by('-ts')[:20]
    last_run = IngestRun.objects.first()

    last_candle_time = latest.ts if latest else None
    last_candle_time_ist = _format_market_time(last_candle_time)
    since = timezone.now() - timedelta(minutes=60)
    candles_last_60m = Ohlc1m.objects.filter(ts__gte=since).count()

    pipeline = _pipeline_status(latest, candles_last_60m)

    news_24h_since = timezone.now() - timedelta(hours=24)
    news_count = NewsItem.objects.filter(published_at__gte=news_24h_since).count()
    news_sentiment_avg = NewsItem.objects.filter(published_at__gte=news_24h_since).aggregate(
        avg=Avg('sentiment')
    )['avg']

    now_ist = _ist_now()
    announcements_7d_since = now_ist - timedelta(days=7)
    announcements_24h_since = now_ist - timedelta(hours=24)
    announcements_7d_qs = Announcement.objects.filter(published_at__gte=announcements_7d_since)
    announcements_24h_qs = Announcement.objects.filter(published_at__gte=announcements_24h_since)
    announcements_count = announcements_7d_qs.count()
    announcements_24h_count = announcements_24h_qs.count()
    latest_announcement = Announcement.objects.order_by('-published_at').first()
    last_events_run = EventsFetchRun.objects.first()

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
            'data_ok': pipeline['status'] == 'ok',
            'pipeline_status': pipeline['status'],
            'pipeline_reason': pipeline['reason'],
            'ticker': settings.JSLL_TICKER,
            'market_tz': settings.JSLL_MARKET_TZ,
            'news_24h_count': news_count,
            'news_24h_sentiment_avg': news_sentiment_avg,
            'announcements_7d_count': announcements_count,
            'announcements_24h_count': announcements_24h_count,
            'latest_announcement': latest_announcement,
            'events_last_run': last_events_run,
        },
    )


class HealthView(APIView):
    serializer_class = HealthResponseSerializer

    @extend_schema(responses=HealthResponseSerializer)
    def get(self, request):
        return Response({'status': 'ok'})


class MetaView(APIView):
    serializer_class = MetaResponseSerializer

    @extend_schema(responses=MetaResponseSerializer)
    def get(self, request):
        return Response({'app': 'JSLL Decision Intelligence', 'version': '0.1.0'})


class Ohlc1mView(APIView):
    serializer_class = OhlcCandleSerializer

    @extend_schema(responses=OhlcCandleSerializer(many=True))
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
    serializer_class = LatestQuoteSerializer

    @extend_schema(responses=LatestQuoteSerializer)
    def get(self, request):
        latest = Ohlc1m.objects.order_by('-ts').first()
        now_server, seconds_since = _freshness(latest)
        if latest is None:
            return Response(
                {
                    'ticker': settings.JSLL_TICKER,
                    'last_price': None,
                    'last_candle_time': None,
                    'now_server_time': now_server,
                    'seconds_since_last_candle': seconds_since,
                    'status': 'degraded',
                    'last_candle_time_ist': None,
                }
            )
        freshness_sec, _min_candles = compute_thresholds(timezone.now().astimezone(ZoneInfo(settings.JSLL_MARKET_TZ)))
        status = 'ok' if seconds_since is not None and seconds_since <= freshness_sec else 'degraded'
        return Response(
            {
                'ticker': settings.JSLL_TICKER,
                'last_price': latest.close,
                'last_candle_time': latest.ts,
                'now_server_time': now_server,
                'seconds_since_last_candle': seconds_since,
                'status': status,
                'last_candle_time_ist': _format_market_time(latest.ts),
            }
        )


class PipelineStatusView(APIView):
    serializer_class = PipelineStatusSerializer

    @extend_schema(responses=PipelineStatusSerializer)
    def get(self, request):
        last_run = IngestRun.objects.first()
        latest = Ohlc1m.objects.order_by('-ts').first()
        last_candle_time = latest.ts if latest else None
        since = timezone.now() - timedelta(minutes=60)
        candles_last_60m = Ohlc1m.objects.filter(ts__gte=since).count()

        pipeline = _pipeline_status(latest, candles_last_60m)

        return Response(
            {
                'last_run': _serialize_run(last_run),
                'last_candle_time': last_candle_time,
                'candles_last_60m': candles_last_60m,
                'data_ok': pipeline['status'] == 'ok',
                'ticker': settings.JSLL_TICKER,
                'market_tz': settings.JSLL_MARKET_TZ,
                'now_server_time': pipeline['now_server_time'],
                'seconds_since_last_candle': pipeline['seconds_since_last_candle'],
                'status': pipeline['status'],
                'market_state': pipeline['market_state'],
                'freshness_ok': pipeline['freshness_ok'],
                'completeness_ok': pipeline['completeness_ok'],
                'reason': pipeline['reason'],
                'thresholds': pipeline['thresholds'],
            }
        )


class NewsView(APIView):
    serializer_class = NewsItemSerializer

    @extend_schema(responses=NewsItemSerializer(many=True))
    def get(self, request):
        limit = int(request.query_params.get('limit', 50))
        limit = max(1, min(limit, 200))
        items = NewsItem.objects.order_by('-published_at')[:limit]
        payload = [
            {
                'published_at': item.published_at,
                'source': item.source,
                'title': item.title,
                'url': item.url,
                'summary': item.summary,
                'sentiment': item.sentiment,
                'relevance': item.relevance,
                'entities_json': item.entities_json,
            }
            for item in items
        ]
        return Response(payload)


class AnnouncementsView(APIView):
    serializer_class = AnnouncementSerializer

    @extend_schema(responses=AnnouncementSerializer(many=True))
    def get(self, request):
        limit = int(request.query_params.get('limit', 50))
        limit = max(1, min(limit, 200))
        items = Announcement.objects.order_by('-published_at')[:limit]
        payload = [
            {
                'published_at': item.published_at,
                'headline': item.headline,
                'url': item.url,
                'type': item.type,
                'polarity': item.polarity,
                'impact_score': item.impact_score,
                'tags_json': item.tags_json,
            }
            for item in items
        ]
        return Response(payload)


class EventsSummaryView(APIView):
    serializer_class = EventsSummarySerializer

    @extend_schema(responses=EventsSummarySerializer)
    def get(self, request):
        news_24h_since = timezone.now() - timedelta(hours=24)
        news_last_24h = NewsItem.objects.filter(published_at__gte=news_24h_since)
        news_count = news_last_24h.count()
        news_sentiment_avg = news_last_24h.aggregate(avg=Avg('sentiment'))['avg'] or 0.0

        now_ist = _ist_now()
        announcements_7d_since = now_ist - timedelta(days=7)
        announcements_24h_since = now_ist - timedelta(hours=24)
        announcements_last_7d = Announcement.objects.filter(published_at__gte=announcements_7d_since)
        announcements_last_24h = Announcement.objects.filter(published_at__gte=announcements_24h_since)

        announcements_count = announcements_last_7d.count()
        announcements_24h_count = announcements_last_24h.count()
        impact_sum_24h = announcements_last_24h.aggregate(total=Sum('impact_score'))['total'] or 0
        impact_sum_7d = announcements_last_7d.aggregate(total=Sum('impact_score'))['total'] or 0
        negative_impact_7d = announcements_last_7d.filter(impact_score__lt=0).aggregate(total=Sum('impact_score'))['total'] or 0

        latest_announcement = Announcement.objects.order_by('-published_at').first()
        last_fetch_run = EventsFetchRun.objects.first()

        return Response(
            {
                'news_last_24h_count': news_count,
                'news_last_24h_sentiment_avg': news_sentiment_avg,
                'announcements_last_7d_count': announcements_count,
                'announcements_last_24h_count': announcements_24h_count,
                'announcements_impact_sum_24h': impact_sum_24h,
                'announcements_impact_sum_7d': impact_sum_7d,
                'announcements_negative_impact_sum_7d': negative_impact_7d,
                'latest_announcement': {
                    'published_at': latest_announcement.published_at,
                    'headline': latest_announcement.headline,
                    'url': latest_announcement.url,
                    'type': latest_announcement.type,
                    'polarity': latest_announcement.polarity,
                    'impact_score': latest_announcement.impact_score,
                } if latest_announcement else None,
                'last_fetch_run': _serialize_events_run(last_fetch_run),
            }
        )