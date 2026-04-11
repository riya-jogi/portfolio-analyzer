"""
Market data helpers: normalize Indian tickers and fetch last price via yfinance.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import yfinance as yf

logger = logging.getLogger(__name__)


def normalize_ticker(stock_name: str) -> str:
    """
    Strip whitespace. If symbol already ends with .NS or .BO, use as-is;
    otherwise append .NS (NSE), e.g. RELIANCE -> RELIANCE.NS
    """
    s = (stock_name or "").strip().upper()
    if not s:
        return s
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def fetch_last_close(ticker: str) -> Decimal | None:
    """
    Return last available close price as Decimal, or None if unavailable.
    Handles network/delisted symbols without raising to callers.
    """
    if not ticker:
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            last = hist["Close"].iloc[-1]
            if last is not None:
                return Decimal(str(round(float(last), 4)))
        # Some tickers expose last_price in fast_info
        fi = getattr(t, "fast_info", None) or {}
        lp = fi.get("last_price") or fi.get("previous_close")
        if lp is not None:
            return Decimal(str(round(float(lp), 4)))
    except Exception as e:
        logger.warning("yfinance failed for %s: %s", ticker, e)
    return None
