"""IDX trading days: weekdays that are not exchange holidays.

Holidays come from market.holidays (or a CSV for local work). Fill them from IDX's official
holiday announcement each year; this module never guesses them.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path


def load_holidays_csv(path: Path) -> set[date]:
    """CSV with columns: holiday_date (YYYY-MM-DD), description."""
    with path.open(newline="", encoding="utf-8") as f:
        return {date.fromisoformat(row["holiday_date"]) for row in csv.DictReader(f)}


def is_trading_day(day: date, holidays: Iterable[date]) -> bool:
    return day.weekday() < 5 and day not in set(holidays)


def trading_days(start: date, end: date, holidays: Iterable[date]) -> Iterator[date]:
    hol = set(holidays)
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in hol:
            yield day
        day += timedelta(days=1)
