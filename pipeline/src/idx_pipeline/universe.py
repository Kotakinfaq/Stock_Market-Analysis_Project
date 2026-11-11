"""Kompas100 membership, point in time.

Each review period is one CSV in data/kompas100/, named <period_start>.csv (e.g. 2026-08-01.csv),
with a single column `ticker`. Copy the lists from IDX's official index announcements; keep every
past period so backtests use the members as they were, not today's survivors.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import tickers


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    members: frozenset[str]


def load_periods(directory: Path) -> list[Period]:
    periods: list[Period] = []
    for path in sorted(directory.glob("*.csv")):
        start = date.fromisoformat(path.stem)
        with path.open(newline="", encoding="utf-8") as f:
            members = frozenset(tickers.normalize(row["ticker"]) for row in csv.DictReader(f))
        if not members:
            raise ValueError(f"{path.name} has no tickers")
        periods.append(Period(start, members))
    return periods


def members_on(day: date, periods: list[Period]) -> frozenset[str]:
    """The members in force on `day`: the latest period starting on or before it."""
    current = [p for p in periods if p.start <= day]
    if not current:
        raise LookupError(f"No membership period covers {day.isoformat()}")
    return max(current, key=lambda p: p.start).members
