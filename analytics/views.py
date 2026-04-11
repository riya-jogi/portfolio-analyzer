"""
Portfolio analytics: investment totals, live values, P/L, XIRR.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from portfolio.models import Holding
from pyxirr import xirr
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AnalysisResponseSerializer, AnalysisSummarySerializer, StockPerformanceSerializer
from .services import fetch_last_close, normalize_ticker

# Match DRF DecimalField decimal_places for API output (avoids 400 validation errors).
_D4 = Decimal("0.0001")
_D6 = Decimal("0.000001")
_D8 = Decimal("0.00000001")


def _dec4(x: Decimal) -> Decimal:
    return x.quantize(_D4, rounding=ROUND_HALF_UP)


def _dec6(x: Decimal) -> Decimal:
    return x.quantize(_D6, rounding=ROUND_HALF_UP)


def _row_pct(pl: Decimal, inv: Decimal) -> Decimal | None:
    """Return P/L % (quantized); serializer allows max_digits=24."""
    if inv <= 0:
        return None
    try:
        return (pl / inv * Decimal("100")).quantize(_D4, rounding=ROUND_HALF_UP)
    except Exception:
        return None


class PortfolioAnalysisView(APIView):
    """GET: aggregated metrics and per-row performance for the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        holdings = list(Holding.objects.filter(user=request.user).order_by("buy_date"))
        today = timezone.now().date()
        stocks_data = []
        total_investment = Decimal("0")
        current_value_total = Decimal("0")
        priced_count = 0

        # First pass: fetch prices and build rows
        for h in holdings:
            qty = _dec6(h.quantity)
            bp = _dec4(h.buy_price)
            inv = _dec4(qty * bp)
            total_investment += inv
            ticker_used = normalize_ticker(h.stock_name)
            price = fetch_last_close(ticker_used) if ticker_used else None
            price_ok = price is not None
            if price is not None:
                price = _dec4(price)
            if price_ok:
                priced_count += 1
                cv = _dec4(qty * price)
                current_value_total += cv
                pl = _dec4(cv - inv)
                pl_pct = _row_pct(pl, inv)
            else:
                cv = None
                pl = None
                pl_pct = None

            stocks_data.append(
                {
                    "stock_name": str(h.stock_name).strip(),
                    "ticker_used": ticker_used,
                    "quantity": qty,
                    "buy_price": bp,
                    "buy_date": h.buy_date,
                    "investment": inv,
                    "current_price": price,
                    "current_value": cv,
                    "profit_loss": pl,
                    "profit_loss_percent": pl_pct,
                    "price_available": price_ok,
                }
            )

        # Totals: P/L only on known current values; % vs total investment
        total_investment = _dec4(total_investment)
        current_value_total = _dec4(current_value_total)
        profit_loss = _dec4(current_value_total - total_investment)
        if total_investment > 0:
            profit_loss_percent = _row_pct(profit_loss, total_investment)
        else:
            profit_loss_percent = None

        # XIRR: all lots must have live price for a consistent IRR
        xirr_val = None
        xirr_err = None
        if not holdings:
            xirr_err = "No holdings."
        elif priced_count != len(holdings):
            xirr_err = "XIRR requires a live price for every holding."
        else:
            # One net outflow per calendar date (multiple lots on same day are combined).
            by_date: defaultdict[date, float] = defaultdict(float)
            for h in holdings:
                by_date[h.buy_date] += float(-(h.quantity * h.buy_price))
            dates_cf = sorted(by_date.keys()) + [today]
            amounts_cf = [by_date[d] for d in sorted(by_date.keys())] + [float(current_value_total)]
            try:
                r = xirr(dates_cf, amounts_cf)
                if r is not None:
                    rf = float(r)
                    if math.isnan(rf) or math.isinf(rf):
                        xirr_val = None
                        xirr_err = "XIRR returned a non-finite value."
                    else:
                        xirr_val = Decimal(str(rf)).quantize(_D8, rounding=ROUND_HALF_UP)
            except Exception as e:
                xirr_err = str(e)

        summary = {
            "total_investment": total_investment,
            "current_value": current_value_total,
            "profit_loss": profit_loss,
            "profit_loss_percent": profit_loss_percent,
            "priced_holdings_count": priced_count,
            "total_holdings_count": len(holdings),
            "xirr": xirr_val,
            "xirr_error": xirr_err,
        }

        # Validate through serializers for stable schema
        sum_ser = AnalysisSummarySerializer(data=summary)
        sum_ser.is_valid(raise_exception=True)
        st_ser = StockPerformanceSerializer(data=stocks_data, many=True)
        st_ser.is_valid(raise_exception=True)
        out = {
            "success": True,
            "summary": sum_ser.validated_data,
            "stocks": st_ser.validated_data,
        }
        final = AnalysisResponseSerializer(data=out)
        final.is_valid(raise_exception=True)
        return Response(final.validated_data)
