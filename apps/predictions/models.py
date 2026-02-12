from django.db import models


class PricePredictionRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    train_start = models.DateTimeField(null=True, blank=True)
    train_end = models.DateTimeField(null=True, blank=True)
    test_start = models.DateTimeField(null=True, blank=True)
    test_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='ok')
    notes = models.TextField(blank=True, default='')
    metrics_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PredictionRun {self.id} {self.status}"


class PricePrediction(models.Model):
    ts = models.DateTimeField(db_index=True)
    horizon_min = models.IntegerField()
    predicted_return = models.FloatField()
    predicted_price = models.FloatField()
    last_close = models.FloatField()
    model_name = models.CharField(max_length=50)
    confidence = models.FloatField(null=True, blank=True)
    run = models.ForeignKey(
        PricePredictionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='predictions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ts']
        constraints = [
            models.UniqueConstraint(fields=['ts', 'horizon_min'], name='uniq_prediction_ts_horizon'),
        ]

    def __str__(self):
        return f"Prediction {self.ts} {self.horizon_min}m"
