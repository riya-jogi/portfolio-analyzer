from decimal import Decimal

from rest_framework import serializers


class StockPerformanceSerializer(serializers.Serializer):
    """Per-holding performance line."""

    stock_name = serializers.CharField()
    ticker_used = serializers.CharField(allow_blank=True)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6)
    buy_price = serializers.DecimalField(max_digits=18, decimal_places=4)
    buy_date = serializers.DateField()
    investment = serializers.DecimalField(max_digits=24, decimal_places=4)
    current_price = serializers.DecimalField(
        max_digits=18, decimal_places=4, allow_null=True, required=False
    )
    current_value = serializers.DecimalField(
        max_digits=24, decimal_places=4, allow_null=True, required=False
    )
    profit_loss = serializers.DecimalField(max_digits=24, decimal_places=4, allow_null=True)
    # Can be huge if average cost is tiny vs live price — allow more digits than 12.
    profit_loss_percent = serializers.DecimalField(max_digits=24, decimal_places=4, allow_null=True)
    price_available = serializers.BooleanField()
    # "live" = Yahoo Finance; "csv" = LTP from uploaded file; "none" = missing both.
    price_source = serializers.ChoiceField(choices=("live", "csv", "none"))


class AnalysisSummarySerializer(serializers.Serializer):
    """Portfolio-level totals."""

    total_investment = serializers.DecimalField(max_digits=24, decimal_places=4)
    # Sum of current market value for holdings with a live quote (unknown prices excluded).
    current_value = serializers.DecimalField(max_digits=24, decimal_places=4)
    profit_loss = serializers.DecimalField(max_digits=24, decimal_places=4)
    profit_loss_percent = serializers.DecimalField(max_digits=24, decimal_places=4, allow_null=True)
    # When portfolio is down: same sign as profit_loss_percent; else null.
    loss_percent = serializers.DecimalField(max_digits=24, decimal_places=4, allow_null=True)
    # Approx. gain % on remaining capital needed to recover from loss_percent (null if not in loss).
    recovery_needed_percent = serializers.DecimalField(max_digits=24, decimal_places=4, allow_null=True)
    priced_holdings_count = serializers.IntegerField()
    total_holdings_count = serializers.IntegerField()
    xirr = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    xirr_error = serializers.CharField(allow_null=True, required=False)


class AnalysisResponseSerializer(serializers.Serializer):
    """Top-level analysis API response."""

    success = serializers.BooleanField()
    summary = AnalysisSummarySerializer()
    holdings = StockPerformanceSerializer(many=True)
    top_gainers = StockPerformanceSerializer(many=True)
    top_losers = StockPerformanceSerializer(many=True)
    insights = serializers.ListField(child=serializers.CharField())
    missing_price_count = serializers.IntegerField()
