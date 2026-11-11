"""Provider interfaces. Nothing outside providers/ imports a vendor library."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import CorporateAction, PriceBar


class PriceProvider(Protocol):
    source: str

    def daily_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]: ...


class CorporateActionProvider(Protocol):
    source: str

    def corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateAction]: ...
