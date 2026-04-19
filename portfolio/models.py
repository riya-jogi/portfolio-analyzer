from django.conf import settings
from django.db import models


class Holding(models.Model):
    """
    One row per lot: user, symbol/name as stored, quantity, buy price, buy date.
    Multiple rows allow multiple purchase dates (useful for XIRR).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    stock_name = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    buy_price = models.DecimalField(max_digits=18, decimal_places=4)
    buy_date = models.DateField()

    class Meta:
        ordering = ["-buy_date"]

    def __str__(self):
        return f"{self.stock_name} x {self.quantity} ({self.user_id})"
