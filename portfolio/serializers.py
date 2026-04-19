from decimal import Decimal

from rest_framework import serializers

from .models import Holding


class HoldingSerializer(serializers.ModelSerializer):
    """Single holding row for responses."""

    class Meta:
        model = Holding
        fields = ("id", "stock_name", "quantity", "buy_price", "buy_date", "csv_ltp")


class UploadSuccessSerializer(serializers.Serializer):
    """Structured success payload after CSV upload."""

    success = serializers.BooleanField()
    message = serializers.CharField()
    holdings_created = serializers.IntegerField()
    holdings = HoldingSerializer(many=True)


class UploadErrorSerializer(serializers.Serializer):
    """Structured error payload for invalid CSV."""

    success = serializers.BooleanField()
    error = serializers.CharField()
    details = serializers.ListField(child=serializers.CharField(), required=False)
