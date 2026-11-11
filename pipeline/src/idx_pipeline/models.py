"""Vendor-neutral records. Every provider adapter converts its data into these."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class PriceBasis(StrEnum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"


class ActionType(StrEnum):
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    BONUS_SHARES = "bonus_shares"
    RIGHTS_ISSUE = "rights_issue"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"


@dataclass(frozen=True, slots=True)
class PriceBar:
    ticker: str  # IDX code without .JK, e.g. "BBCA"
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    volume_shares: int | None  # always shares, never lots
    source: str
    price_basis: PriceBasis
    fetched_at: datetime
    raw_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CorporateAction:
    ticker: str
    action_type: ActionType
    ex_date: date
    source: str
    fetched_at: datetime
    ratio_old: Decimal | None = None
    ratio_new: Decimal | None = None
    cash_amount: Decimal | None = None
    currency: str | None = None
    raw_ref: str | None = None
