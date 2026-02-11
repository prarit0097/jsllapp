from django.db import models


class Ohlc1m(models.Model):
    ts = models.DateTimeField(unique=True, db_index=True)
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField()
    source = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ts']

    def __str__(self):
        return f"{self.ts.isoformat()} O:{self.open} H:{self.high} L:{self.low} C:{self.close}"


class IngestRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    provider_primary = models.CharField(max_length=50)
    provider_fallback = models.CharField(max_length=50)
    primary_ok = models.BooleanField(default=False)
    fallback_ok = models.BooleanField(default=False)
    candles_fetched_primary = models.IntegerField(default=0)
    candles_fetched_fallback = models.IntegerField(default=0)
    candles_saved = models.IntegerField(default=0)
    missing_filled = models.IntegerField(default=0)
    outliers_rejected = models.IntegerField(default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"IngestRun {self.started_at.isoformat()} primary_ok={self.primary_ok} fallback_ok={self.fallback_ok}"