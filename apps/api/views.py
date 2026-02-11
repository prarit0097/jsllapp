from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.market.models import Ohlc1m


def dashboard(request):
    latest = Ohlc1m.objects.order_by('-ts').first()
    recent = Ohlc1m.objects.order_by('-ts')[:10]
    return render(
        request,
        'dashboard.html',
        {
            'latest': latest,
            'recent': recent,
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
        if latest is None:
            return Response(
                {
                    'last_price': None,
                    'last_candle_time': None,
                    'status': 'no_data',
                }
            )
        return Response(
            {
                'last_price': latest.close,
                'last_candle_time': latest.ts,
                'status': 'ok',
            }
        )