from django.db import models

class Holding(models.Model):
    stock_name = models.CharField(max_length=100)
    quantity = models.FloatField()
    buy_price = models.FloatField()

    def __str__(self):
        return self.stock_name
