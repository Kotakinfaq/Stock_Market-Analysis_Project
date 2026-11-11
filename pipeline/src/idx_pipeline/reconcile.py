"""Daily cross-source check: compare one day's closes from two sources and list the problems.

This catches bad vendor data and adjustment errors before anything is scored or written about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import PriceBar
from .units import looks_like_lot_mismatch

DEFAULT_THRESHOLD_PCT = Decimal("0.5")


@dataclass(frozen=True, slots=True)
class Issue:
    trade_date: date
    ticker: str
    source_a: str
    source_b: str
    issue: str  # close_gap | missing_in_a | missing_in_b | volume_unit
    close_a: Decimal | None = None
    close_b: Decimal | None = None
    diff_pct: Decimal | None = None


def compare(
    trade_date: date,
    bars_a: list[PriceBar],
    bars_b: list[PriceBar],
    expected: frozenset[str],
    source_a: str,
    source_b: str,
    threshold_pct: Decimal = DEFAULT_THRESHOLD_PCT,
) -> list[Issue]:
    a = {b.ticker: b for b in bars_a if b.trade_date == trade_date}
    b = {x.ticker: x for x in bars_b if x.trade_date == trade_date}
    issues: list[Issue] = []

    for ticker in sorted(expected):
        bar_a, bar_b = a.get(ticker), b.get(ticker)
        if bar_a is None:
            issues.append(Issue(trade_date, ticker, source_a, source_b, "missing_in_a",
                                close_b=bar_b.close if bar_b else None))
        if bar_b is None:
            issues.append(Issue(trade_date, ticker, source_a, source_b, "missing_in_b",
                                close_a=bar_a.close if bar_a else None))
        if bar_a is None or bar_b is None:
            continue

        diff_pct = abs(bar_a.close - bar_b.close) / bar_b.close * 100
        if diff_pct > threshold_pct:
            issues.append(Issue(trade_date, ticker, source_a, source_b, "close_gap",
                                bar_a.close, bar_b.close, diff_pct.quantize(Decimal("0.0001"))))
        if looks_like_lot_mismatch(bar_a.volume_shares, bar_b.volume_shares):
            issues.append(Issue(trade_date, ticker, source_a, source_b, "volume_unit",
                                bar_a.close, bar_b.close))
    return issues


def missing_tickers(trade_date: date, bars: list[PriceBar], expected: frozenset[str]) -> list[str]:
    """Completeness check for a single source."""
    have = {b.ticker for b in bars if b.trade_date == trade_date}
    return sorted(expected - have)
