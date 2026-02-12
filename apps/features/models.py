from django.db import models


class Feature1m(models.Model):
    ts = models.DateTimeField(unique=True, db_index=True)
    feature_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ts']

    def __str__(self):
        return f"Feature1m {self.ts.isoformat()}"


class SignalScore(models.Model):
    ts = models.DateTimeField(unique=True, db_index=True)
    price_action_score = models.IntegerField(default=50)
    volume_score = models.IntegerField(default=50)
    news_score = models.IntegerField(default=50)
    announcements_score = models.IntegerField(default=50)
    regime_score = models.IntegerField(default=50)
    overall_score = models.IntegerField(default=50)
    explain_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ts']

    def __str__(self):
        return f"SignalScore {self.ts.isoformat()}"
