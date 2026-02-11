from django.db import models


class NewsItem(models.Model):
    published_at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    url = models.URLField(unique=True)
    summary = models.TextField(blank=True, default='')
    sentiment = models.FloatField(default=0.0)
    relevance = models.FloatField(default=1.0)
    entities_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return f"{self.published_at.isoformat()} {self.title}"


class Announcement(models.Model):
    published_at = models.DateTimeField(db_index=True)
    headline = models.CharField(max_length=500)
    url = models.URLField(blank=True, default='')
    type = models.CharField(max_length=50, default='other')
    polarity = models.IntegerField(default=0)
    impact_score = models.IntegerField(default=0)
    low_priority = models.BooleanField(default=False)
    dedupe_hash = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    dedupe_key = models.CharField(max_length=64, unique=True, db_index=True, blank=True, null=True)
    tags_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return f"{self.published_at.isoformat()} {self.headline}"


class EventsFetchRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    news_ok = models.BooleanField(default=False)
    announcements_ok = models.BooleanField(default=False)
    news_fetched = models.IntegerField(default=0)
    announcements_fetched = models.IntegerField(default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"EventsFetchRun {self.started_at.isoformat()}"
