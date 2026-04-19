import io
import logging
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Holding
from .serializers import HoldingSerializer, UploadErrorSerializer, UploadSuccessSerializer

logger = logging.getLogger("portfolio.upload")

# Logical columns required after normalization (see _normalize_dataframe_columns).
REQUIRED_COLUMNS = ["stock_name", "quantity", "buy_price", "buy_date"]

# After lowercasing + underscores, these names map to our canonical keys.
_COLUMN_ALIASES = {
    "symbol": "stock_name",
    "ticker": "stock_name",
    "stock": "stock_name",
    "stockname": "stock_name",
    "name": "stock_name",
    "instrument": "stock_name",
    "scrip": "stock_name",
    "qty": "quantity",
    "shares": "quantity",
    "units": "quantity",
    "purchase_price": "buy_price",
    "avg_price": "buy_price",
    "average_price": "buy_price",
    "price": "buy_price",
    "cost": "buy_price",
    "purchase_date": "buy_date",
    "acquisition_date": "buy_date",
    "trade_date": "buy_date",
    "date": "buy_date",
    # Broker / Zerodha-style holdings export
    "avg_cost": "buy_price",
    "average_cost": "buy_price",
    "cost_price": "buy_price",
    "buy_avg": "buy_price",
}


def _normalize_header(name: str) -> str:
    """
    Strip BOM; lowercase; turn punctuation into word breaks so broker headers match.
    Examples: 'Qty.' -> 'qty', 'Avg. cost' -> 'avg_cost', 'Net chg.' -> 'net_chg'.
    """
    s = str(name).strip().lstrip("\ufeff").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = "_".join(t for t in s.split() if t)
    return s.replace("-", "_")


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names so uploads work with BOM, casing, and spaces."""
    # Drop empty header columns (trailing commas in broker CSVs)
    df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]].copy()
    rename: dict[str, str] = {}
    mapping_notes: list[str] = []
    for c in df.columns:
        old_repr = repr(str(c))
        key = _normalize_header(c)
        before_alias = key
        key = _COLUMN_ALIASES.get(key, key)
        rename[c] = key
        if before_alias != key:
            mapping_notes.append(f"{old_repr} normalized={before_alias!r} alias->{key!r}")
        elif str(c).strip() != key or old_repr != repr(key):
            mapping_notes.append(f"{old_repr} -> {key!r}")

    out = df.rename(columns=rename)
    targets = list(rename.values())
    dup_targets = [k for k, n in Counter(targets).items() if n > 1]
    if dup_targets:
        logger.warning(
            "Duplicate column targets after normalize (ambiguous merge): %s — columns=%s",
            dup_targets,
            [str(x) for x in out.columns.tolist()],
        )
    logger.info(
        "Column normalization: %d cols; mapping: %s",
        len(rename),
        "; ".join(mapping_notes) if mapping_notes else "(identity)",
    )
    return out


def _apply_default_buy_date_if_missing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Zerodha/Kite-style exports often omit purchase date.
    Default all rows to today's date in the project timezone and log a warning.
    """
    if "buy_date" in df.columns:
        return df
    d = timezone.now().date()
    logger.warning(
        "No buy_date column found (typical for broker holdings export). "
        "Defaulting every row to buy_date=%s. Add buy_date for accurate XIRR.",
        d,
    )
    out = df.copy()
    out["buy_date"] = d
    return out


def _decode_upload_bytes(raw: bytes) -> tuple[str, str]:
    """Decode bytes; returns (text, encoding_label). Tries Excel-friendly encodings."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            return text, enc
        except UnicodeDecodeError:
            continue
    text = raw.decode("utf-8", errors="replace")
    return text, "utf-8 (errors=replace)"


def _drop_trailing_empty_excel_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove trailing Unnamed: N columns that are all empty (common Excel export quirk)."""
    cols = list(df.columns)
    while cols and str(cols[-1]).startswith("Unnamed") and df[cols[-1]].isna().all():
        cols.pop()
    return df[cols] if cols else df


def _read_portfolio_csv(raw: bytes) -> pd.DataFrame:
    """
    Parse CSV with automatic delimiter detection.
    Semicolon and tab are common when comma-separated parsing yields a single column.
    """
    text, enc_label = _decode_upload_bytes(raw)
    text = text.strip()
    if not text:
        logger.error("Upload decode produced empty text (encoding=%s)", enc_label)
        raise ValueError("File is empty")

    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    first_line = text.splitlines()[0] if text else ""
    logger.info(
        "CSV decode: encoding=%s bytes=%d lines~=%d first_line=%r",
        enc_label,
        len(raw),
        line_count,
        first_line[:400] + ("…" if len(first_line) > 400 else ""),
    )

    attempts: list[dict] = [
        {"sep": None, "engine": "python"},
        {"sep": ",", "engine": "c"},
        {"sep": ";", "engine": "c"},
        {"sep": "\t", "engine": "c"},
    ]
    if first_line.count(";") > first_line.count(",") and ";" in first_line:
        attempts.insert(0, {"sep": ";", "engine": "c"})

    last_error: Exception | None = None
    best: pd.DataFrame | None = None
    best_n = 0
    attempt_logs: list[str] = []

    for kw in attempts:
        label = f"sep={kw['sep']!r} engine={kw['engine']!r}"
        try:
            df_try = pd.read_csv(io.StringIO(text), **kw)
            df_try = _drop_trailing_empty_excel_columns(df_try)
            n = len(df_try.columns)
            cols_preview = [str(x) for x in df_try.columns.tolist()][:20]
            attempt_logs.append(f"{label} -> cols={n} headers={cols_preview!s}")
            if n > best_n:
                best_n = n
                best = df_try
            if n >= len(REQUIRED_COLUMNS):
                logger.info("CSV parse OK using %s; columns=%s", label, cols_preview)
                return df_try
        except Exception as e:
            last_error = e
            attempt_logs.append(f"{label} FAILED: {type(e).__name__}: {e}")
            logger.debug("Parse attempt failed: %s", label, exc_info=True)

    logger.warning("All full-column parse attempts finished without 4+ cols. Attempts:\n  %s", "\n  ".join(attempt_logs))
    if best is not None:
        logger.info(
            "Falling back to best parse: cols=%d headers=%s",
            best_n,
            [str(x) for x in best.columns.tolist()],
        )
        return best
    err = last_error if last_error else ValueError("Could not parse CSV")
    logger.error("CSV parse failed completely: %s", err)
    raise err


class CsvUploadView(APIView):
    """
    POST multipart file: replaces all holdings for the user with CSV contents.
    Columns: stock_name, quantity, buy_price, buy_date
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            logger.warning("Upload rejected: no file in request (user=%s)", getattr(request.user, "pk", None))
            body = {"success": False, "error": "No file provided.", "details": ["Use form field name 'file'."]}
            ser = UploadErrorSerializer(data=body)
            ser.is_valid(raise_exception=True)
            return Response(ser.validated_data, status=400)

        fname = getattr(upload, "name", "")
        size = getattr(upload, "size", None)
        uid = getattr(request.user, "pk", None)
        uemail = getattr(request.user, "email", "")
        logger.info("CSV upload start user_id=%s email=%r name=%r size=%s", uid, uemail, fname, size)

        try:
            raw = upload.read()
            logger.info("Read %d bytes from upload", len(raw))
            df = _read_portfolio_csv(raw)
            df = _normalize_dataframe_columns(df)
            df = _apply_default_buy_date_if_missing(df)
        except Exception as e:
            logger.exception("CSV read/normalize failed for user_id=%s file=%r", uid, fname)
            details = (
                [repr(e)]
                if settings.DEBUG
                else ["See server logs for details (logger portfolio.upload)."]
            )
            body = {"success": False, "error": "Could not parse CSV.", "details": details}
            ser = UploadErrorSerializer(data=body)
            ser.is_valid(raise_exception=True)
            return Response(ser.validated_data, status=400)

        seen = [str(x) for x in df.columns]
        logger.info("After normalize: column_count=%d columns=%s row_count=%d", len(seen), seen, len(df.index))

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            logger.error(
                "Missing required columns user_id=%s missing=%s required=%s got=%s",
                uid,
                missing,
                REQUIRED_COLUMNS,
                seen,
            )
            body = {
                "success": False,
                "error": "Missing required columns.",
                "details": [
                    f"Missing: {', '.join(missing)}. Required: {', '.join(REQUIRED_COLUMNS)}.",
                    f"Columns found after normalization: {', '.join(seen)}",
                    "Check the Django console for full decode/parse logs (logger portfolio.upload).",
                ],
            }
            ser = UploadErrorSerializer(data=body)
            ser.is_valid(raise_exception=True)
            return Response(ser.validated_data, status=400)

        if df.empty:
            logger.error("CSV has header but zero data rows user_id=%s", uid)
            body = {"success": False, "error": "CSV has no data rows.", "details": []}
            ser = UploadErrorSerializer(data=body)
            ser.is_valid(raise_exception=True)
            return Response(ser.validated_data, status=400)

        rows_errors: list[str] = []
        to_create: list[Holding] = []

        for idx, row in df.iterrows():
            line = int(idx) + 2  # 1-based + header
            try:
                stock_name = str(row["stock_name"]).strip()
                if not stock_name or stock_name.lower() == "nan":
                    rows_errors.append(f"Row {line}: invalid stock_name")
                    continue

                qty = row["quantity"]
                if pd.isna(qty):
                    rows_errors.append(f"Row {line}: quantity is empty")
                    continue
                quantity = Decimal(str(qty).strip())

                bp = row["buy_price"]
                if pd.isna(bp):
                    rows_errors.append(f"Row {line}: buy_price is empty")
                    continue
                buy_price = Decimal(str(bp).strip())

                bd = row["buy_date"]
                if pd.isna(bd):
                    rows_errors.append(f"Row {line}: buy_date is empty")
                    continue
                if hasattr(bd, "to_pydatetime"):
                    buy_date = pd.Timestamp(bd).date()
                else:
                    parsed = pd.to_datetime(str(bd), dayfirst=True, errors="coerce")
                    if pd.isna(parsed):
                        rows_errors.append(f"Row {line}: could not parse buy_date")
                        continue
                    buy_date = parsed.date()

                if quantity <= 0 or buy_price < 0:
                    rows_errors.append(f"Row {line}: quantity must be > 0 and buy_price >= 0")
                    continue

            except (InvalidOperation, ValueError, TypeError) as e:
                rows_errors.append(f"Row {line}: {e}")
                continue

            to_create.append(
                Holding(
                    user=request.user,
                    stock_name=stock_name,
                    quantity=quantity,
                    buy_price=buy_price,
                    buy_date=buy_date,
                )
            )

        if rows_errors and not to_create:
            logger.error(
                "No valid rows after row scan user_id=%s errors(first 10)=%s",
                uid,
                rows_errors[:10],
            )
            body = {"success": False, "error": "No valid rows to import.", "details": rows_errors[:50]}
            ser = UploadErrorSerializer(data=body)
            ser.is_valid(raise_exception=True)
            return Response(ser.validated_data, status=400)

        with transaction.atomic():
            Holding.objects.filter(user=request.user).delete()
            Holding.objects.bulk_create(to_create)

        holdings = list(Holding.objects.filter(user=request.user).order_by("-buy_date"))
        msg = "Portfolio replaced successfully."
        if rows_errors:
            msg += f" Skipped {len(rows_errors)} invalid row(s)."

        payload = {
            "success": True,
            "message": msg,
            "holdings_created": len(holdings),
            "holdings": HoldingSerializer(holdings, many=True).data,
        }
        out = UploadSuccessSerializer(data=payload)
        out.is_valid(raise_exception=True)
        logger.info(
            "CSV upload OK user_id=%s holdings_created=%d skipped_rows=%d",
            uid,
            len(holdings),
            len(rows_errors),
        )
        return Response(out.validated_data, status=200)
