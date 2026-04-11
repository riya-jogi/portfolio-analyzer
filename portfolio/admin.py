from django.contrib import admin

from .models import Holding


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ("stock_name", "user", "quantity", "buy_price", "buy_date")
    list_filter = ("buy_date",)
    search_fields = ("stock_name", "user__email")
