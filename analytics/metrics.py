"""
Portfolio metrics: recovery math after drawdown, top movers, rule-based insights.

Recovery formula: to break even after a loss of L% (negative portfolio return),
gain needed ≈ |L| / (100 - |L|) * 100 on the remaining capital (not compound-perfect but standard heuristic).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_D4 = Decimal("0.0001")
_D6 = Decimal("0.000001")


def recovery_needed_percent_from_loss_percent(loss_percent: Decimal) -> Decimal | None:
    """
    `loss_percent` is negative (e.g. -20 for 20% portfolio drawdown).
    Returns the approximate recovery gain % needed, or None if undefined (|L| >= 100).
    """
    abs_lp = abs(loss_percent)
    if abs_lp >= Decimal("100"):
        return None
    try:
        return (abs_lp / (Decimal("100") - abs_lp) * Decimal("100")).quantize(
            _D4, rounding=ROUND_HALF_UP
        )
    except Exception:
        return None


def portfolio_loss_and_recovery(
    profit_loss_percent: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """
    When the portfolio P/L % is negative, expose it as `loss_percent` (same sign as P/L %)
    and compute `recovery_needed_percent`. Otherwise both are None.
    """
    if profit_loss_percent is None or profit_loss_percent >= 0:
        return None, None
    lp = profit_loss_percent
    return lp, recovery_needed_percent_from_loss_percent(lp)


def _row_pct(pl: Decimal, inv: Decimal) -> Decimal | None:
    if inv <= 0:
        return None
    try:
        return (pl / inv * Decimal("100")).quantize(_D4, rounding=ROUND_HALF_UP)
    except Exception:
        return None


def aggregate_holdings_by_stock(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    One line per stock_name: summed qty/investment/current value and blended P/L.
    Matches StockPerformanceSerializer shape for top movers.
    """
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get("stock_name", "")).strip()].append(r)

    out: list[dict[str, Any]] = []
    for name, grp in groups.items():
        if not name:
            continue
        qty = sum((_D(g["quantity"]) for g in grp), start=Decimal("0"))
        inv = sum((_D(g["investment"]) for g in grp), start=Decimal("0"))
        all_priced = all(g.get("price_available") for g in grp)
        ticker_used = next(
            (str(g.get("ticker_used") or "") for g in grp if g.get("ticker_used")), ""
        )
        buy_date = min(g["buy_date"] for g in grp)
        sources = [str(g.get("price_source") or "none") for g in grp]
        if "live" in sources:
            blended_source = "live"
        elif "csv" in sources:
            blended_source = "csv"
        else:
            blended_source = "none"

        if all_priced and qty > 0:
            cv = sum((_D(g["current_value"]) for g in grp), start=Decimal("0"))
            pl = cv - inv
            pl = pl.quantize(_D4, rounding=ROUND_HALF_UP)
            cv = cv.quantize(_D4, rounding=ROUND_HALF_UP)
            inv_q = inv.quantize(_D4, rounding=ROUND_HALF_UP)
            qty_q = qty.quantize(_D6, rounding=ROUND_HALF_UP)
            pl_pct = _row_pct(pl, inv_q)
            price = (cv / qty_q).quantize(_D4, rounding=ROUND_HALF_UP)
            bp = (inv_q / qty_q).quantize(_D4, rounding=ROUND_HALF_UP)
            out.append(
                {
                    "stock_name": name,
                    "ticker_used": ticker_used,
                    "quantity": qty_q,
                    "buy_price": bp,
                    "buy_date": buy_date,
                    "investment": inv_q,
                    "current_price": price,
                    "current_value": cv,
                    "profit_loss": pl,
                    "profit_loss_percent": pl_pct,
                    "price_available": True,
                    "price_source": blended_source,
                }
            )
        else:
            inv_q = inv.quantize(_D4, rounding=ROUND_HALF_UP)
            qty_q = qty.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            out.append(
                {
                    "stock_name": name,
                    "ticker_used": ticker_used,
                    "quantity": qty_q,
                    "buy_price": (inv_q / qty_q).quantize(_D4, rounding=ROUND_HALF_UP)
                    if qty_q > 0
                    else Decimal("0"),
                    "buy_date": buy_date,
                    "investment": inv_q,
                    "current_price": None,
                    "current_value": None,
                    "profit_loss": None,
                    "profit_loss_percent": None,
                    "price_available": False,
                    "price_source": "none",
                }
            )
    return out


def _D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def top_gainers_and_losers(
    rows: list[dict[str, Any]], n: int = 3
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per-stock P/L: top n gainers and top n losers by aggregated profit_loss."""
    per_stock = aggregate_holdings_by_stock(rows)
    priced = [r for r in per_stock if r.get("price_available") and r.get("profit_loss") is not None]
    if not priced:
        return [], []
    gainers = sorted(priced, key=lambda r: r["profit_loss"], reverse=True)[:n]
    losers = sorted(priced, key=lambda r: r["profit_loss"])[:n]
    return gainers, losers


def compute_insights(
    rows: list[dict[str, Any]],
    profit_loss_percent: Decimal | None,
    missing_price_count: int,
    total_holdings: int,
) -> list[str]:
    """
    Rules:
    - Any single priced position > 40% of total priced MV → concentration message.
    - Portfolio P/L % < -30% → heavy drawdown.
    - Missing prices on > 20% of rows → data quality.
    """
    insights: list[str] = []

    # Aggregate current value by stock (multiple CSV lots for same ticker).
    by_stock: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        if not r.get("price_available"):
            continue
        cv = r.get("current_value")
        if cv is None:
            continue
        name = str(r.get("stock_name", "")).strip()
        by_stock[name] += cv

    total_cv = sum(by_stock.values(), start=Decimal("0"))
    if total_cv > 0:
        for name, cv in by_stock.items():
            if cv / total_cv > Decimal("0.4"):
                insights.append(f"High concentration in {name}")

    if profit_loss_percent is not None and profit_loss_percent < Decimal("-30"):
        insights.append("Portfolio under heavy drawdown")

    if total_holdings > 0:
        missing_ratio = Decimal(missing_price_count) / Decimal(total_holdings)
        if missing_ratio > Decimal("0.2"):
            insights.append("Data quality issue: many holdings missing live prices")

    return insights
