"""yfinance adapter. Licence class: research. Yahoo's API is for personal use only, so this is for
backfilling history and research on your own machine, never for data shown to users.

With auto_adjust=False, Yahoo's open/high/low/close are split-adjusted but not dividend-adjusted.
Install with:  uv sync --extra yfinance
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .. import tickers
from ..models import PriceBar, PriceBasis
from ..units import VolumeUnit, to_shares

SOURCE = "yfinance"
VOLUME_UNIT = VolumeUnit.SHARES


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    f = float(value)
    if math.isnan(f):
        return None
    return Decimal(str(round(f, 2)))


def bars_from_rows(ticker: str, rows: Iterable[tuple[date, Mapping[str, Any]]],
                   fetched_at: datetime) -> list[PriceBar]:
    code = tickers.normalize(ticker)
    bars = []
    for day, row in rows:
        close = _dec(row.get("Close"))
        if close is None or close <= 0:
            continue
        volume = row.get("Volume")
        bars.append(PriceBar(
            ticker=code,
            trade_date=day,
            open=_dec(row.get("Open")),
            high=_dec(row.get("High")),
            low=_dec(row.get("Low")),
            close=close,
            volume_shares=to_shares(None if volume is None or math.isnan(volume) else volume, VOLUME_UNIT),
            source=SOURCE,
            price_basis=PriceBasis.SPLIT_ADJUSTED,
            fetched_at=fetched_at,
        ))
    return bars


class YFinanceProvider:
    source = SOURCE

    def __init__(self, max_retries: int = 4) -> None:
        import yfinance  # imported here so the rest of the pipeline never needs it

        self._yf = yfinance
        self._max_retries = max_retries

    def daily_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        for attempt in range(self._max_retries):
            try:
                frame = self._yf.Ticker(tickers.to_yahoo(ticker)).history(
                    start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                    auto_adjust=False, actions=False,
                )
                break
            except Exception:  # yfinance raises assorted errors on rate limits
                if attempt == self._max_retries - 1:
                    raise
                time.sleep(2 ** attempt + random.random())
        fetched_at = datetime.now(UTC)
        rows = ((ts.date(), row) for ts, row in frame.iterrows())
        return bars_from_rows(ticker, rows, fetched_at)
