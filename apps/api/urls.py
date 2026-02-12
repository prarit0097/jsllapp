from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from .views import (
    AnnouncementsView,
    EventsSummaryView,
    HealthView,
    LatestQuoteView,
    MetaView,
    NewsView,
    Ohlc1mView,
    PipelineStatusView,
    PredictionsLatestView,
    ScoresLatestView,
)

urlpatterns = [
    path('health', HealthView.as_view(), name='health'),
    path('meta', MetaView.as_view(), name='meta'),
    path('jsll/ohlc/1m', Ohlc1mView.as_view(), name='ohlc-1m'),
    path('jsll/quote/latest', LatestQuoteView.as_view(), name='quote-latest'),
    path('jsll/pipeline/status', PipelineStatusView.as_view(), name='pipeline-status'),
    path('jsll/news', NewsView.as_view(), name='news'),
    path('jsll/announcements', AnnouncementsView.as_view(), name='announcements'),
    path('jsll/events/summary', EventsSummaryView.as_view(), name='events-summary'),
    path('jsll/scores/latest', ScoresLatestView.as_view(), name='scores-latest'),
    path('jsll/predictions/latest', PredictionsLatestView.as_view(), name='predictions-latest'),
    path('predictions/latest', PredictionsLatestView.as_view(), name='predictions-latest-short'),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
