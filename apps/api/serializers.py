from rest_framework import serializers


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class MetaResponseSerializer(serializers.Serializer):
    app = serializers.CharField()
    version = serializers.CharField()


class OhlcCandleSerializer(serializers.Serializer):
    ts = serializers.DateTimeField()
    open = serializers.FloatField()
    high = serializers.FloatField()
    low = serializers.FloatField()
    close = serializers.FloatField()
    volume = serializers.FloatField()
    source = serializers.CharField()


class LatestQuoteSerializer(serializers.Serializer):
    ticker = serializers.CharField()
    last_price = serializers.FloatField(allow_null=True)
    last_candle_time = serializers.DateTimeField(allow_null=True)
    now_server_time = serializers.DateTimeField(allow_null=True)
    seconds_since_last_candle = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    last_candle_time_ist = serializers.CharField(allow_null=True)


class PipelineStatusSerializer(serializers.Serializer):
    last_run = serializers.DictField(allow_null=True)
    last_candle_time = serializers.DateTimeField(allow_null=True)
    candles_last_60m = serializers.IntegerField()
    data_ok = serializers.BooleanField()
    ticker = serializers.CharField()
    market_tz = serializers.CharField()
    now_server_time = serializers.DateTimeField(allow_null=True)
    seconds_since_last_candle = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    market_state = serializers.CharField()
    freshness_ok = serializers.BooleanField()
    completeness_ok = serializers.BooleanField()
    reason = serializers.CharField()
    thresholds = serializers.DictField()


class NewsItemSerializer(serializers.Serializer):
    published_at = serializers.DateTimeField()
    source = serializers.CharField()
    title = serializers.CharField()
    url = serializers.URLField()
    summary = serializers.CharField()
    sentiment = serializers.FloatField()
    relevance = serializers.FloatField()
    entities_json = serializers.DictField()


class AnnouncementSerializer(serializers.Serializer):
    published_at = serializers.DateTimeField()
    headline = serializers.CharField()
    url = serializers.URLField(allow_blank=True)
    type = serializers.CharField()
    polarity = serializers.IntegerField()
    impact_score = serializers.IntegerField()
    tags_json = serializers.DictField()


class EventsSummarySerializer(serializers.Serializer):
    news_last_24h_count = serializers.IntegerField()
    news_last_24h_sentiment_avg = serializers.FloatField()
    announcements_last_7d_count = serializers.IntegerField()
    latest_announcement = serializers.DictField(allow_null=True)
    last_fetch_run = serializers.DictField(allow_null=True)