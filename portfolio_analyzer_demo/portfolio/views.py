import csv
import logging
import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Holding

logger = logging.getLogger(__name__)


def _norm_key(s):
    if s is None:
        return ""
    s = str(s).strip().lstrip("\ufeff").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def _canonical_fields(raw_row):
    """Map flexible CSV headers to stock_name, quantity, buy_price."""
    flat = {}
    for k, v in raw_row.items():
        nk = _norm_key(k)
        if nk:
            flat[nk] = v

    def pick(*names):
        for n in names:
            if n in flat and flat[n] not in (None, ""):
                return flat[n]
        return None

    stock = pick(
        "stock_name",
        "stock",
        "symbol",
        "ticker",
        "instrument",
        "instrument_name",
        "security",
        "security_name",
        "company",
        "company_name",
        "name",
        "scrip",
        "description",
    )
    qty = pick(
        "quantity",
        "qty",
        "shares",
        "units",
        "volume",
        "quantity_held",
        "net_quantity",
        "balance",
        "no_of_shares",
    )
    price = pick(
        "buy_price",
        "avg_price",
        "average_price",
        "avg_cost",
        "average_cost",
        "purchase_price",
        "purchase_rate",
        "cost",
        "price",
        "buy_average",
    )

    missing = []
    if stock is None:
        missing.append("stock (e.g. stock_name, symbol, ticker)")
    if qty is None:
        missing.append("quantity (e.g. quantity, qty, shares)")
    if price is None:
        missing.append("buy_price (e.g. buy_price, avg_price, price)")
    if missing:
        cols = [repr(k) for k in raw_row if k is not None]
        raise ValueError(
            "Could not find columns for: "
            + ", ".join(missing)
            + f". Headers in file: {cols}"
        )

    def _parse_float(val):
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValueError("empty number")
        t = re.sub(r"[\u20b9$\u00a3\u20ac\s]", "", str(val).strip())
        if not t:
            raise ValueError("empty after strip")
        t = t.replace(",", "")
        return float(t)

    try:
        q = _parse_float(qty)
        p = _parse_float(price)
    except ValueError as exc:
        raise ValueError(
            f"Could not parse quantity or price from {qty!r} / {price!r}: {exc}"
        ) from exc

    return str(stock).strip(), q, p


class UploadCSV(APIView):
    def post(self, request):
        file = request.FILES["file"]
        decoded = file.read().decode("utf-8-sig").splitlines()
        if not decoded:
            return Response(
                {"error": "File is empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sample = "\n".join(decoded[: min(10, len(decoded))])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(decoded, dialect=dialect)

        for row in reader:
            if not row or not any(v not in (None, "") for v in row.values()):
                continue
            try:
                stock_name, quantity, buy_price = _canonical_fields(row)
            except ValueError as e:
                logger.warning("Upload CSV row rejected: %s", e)
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            Holding.objects.create(
                stock_name=stock_name,
                quantity=quantity,
                buy_price=buy_price,
            )

        return Response({"message": "Uploaded"})


class PortfolioAnalysis(APIView):
    def get(self, request):
        holdings = Holding.objects.all()

        total_investment = 0
        total_value = 0

        current_prices = {
            "RELIANCE": 2900,
            "TCS": 3500
        }

        for h in holdings:
            total_investment += h.quantity * h.buy_price
            total_value += h.quantity * current_prices.get(h.stock_name, 0)

        return Response({
            "investment": total_investment,
            "current_value": total_value,
            "profit": total_value - total_investment
        })
