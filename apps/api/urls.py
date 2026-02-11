from django.urls import path

from .views import HealthView, LatestQuoteView, MetaView, Ohlc1mView, PipelineStatusView

urlpatterns = [
    path('health', HealthView.as_view(), name='health'),
    path('meta', MetaView.as_view(), name='meta'),
    path('jsll/ohlc/1m', Ohlc1mView.as_view(), name='ohlc-1m'),
    path('jsll/quote/latest', LatestQuoteView.as_view(), name='quote-latest'),
    path('jsll/pipeline/status', PipelineStatusView.as_view(), name='pipeline-status'),
]