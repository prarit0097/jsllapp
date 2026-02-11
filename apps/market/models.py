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