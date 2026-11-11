"""EODHD adapter: end-of-day prices, splits and dividends for .JK tickers.

Licence class: non_display (personal plans prohibit showing the data to users).

VERIFY with EODHD's documentation or support before trusting these two settings:
  * PRICE_BASIS: whether open/high/low/close from /api/eod are raw or split-adjusted.
  * VOLUME_UNIT: whether volume for .JK tickers is in shares or lots.
The daily cross-source check will show a mismatch if either is wrong.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from .. import tickers
from ..models import ActionType, CorporateAction, PriceBar, PriceBasis
from ..raw_store import RawStore
from ..units import VolumeUnit, to_shares

BASE_URL = "https://eodhd.com/api"
SOURCE = "eodhd"
PRICE_BASIS = PriceBasis.SPLIT_ADJUSTED
VOLUME_UNIT = VolumeUnit.SHARES


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def parse_eod(ticker: str, payload: list[dict[str, Any]], fetched_at: datetime,
              raw_ref: str | None = None) -> list[PriceBar]:
    code = tickers.normalize(ticker)
    bars = []
    for row in payload:
        close = _dec(row.get("close"))
        if close is None or close <= 0:
            continue  # suspended or empty day
        bars.append(PriceBar(
            ticker=code,
            trade_date=date.fromisoformat(row["date"]),
            open=_dec(row.get("open")),
            high=_dec(row.get("high")),
            low=_dec(row.get("low")),
            close=close,
            volume_shares=to_shares(row.get("volume"), VOLUME_UNIT),
            source=SOURCE,
            price_basis=PRICE_BASIS,
            fetched_at=fetched_at,
            raw_ref=raw_ref,
        ))
    return bars


def parse_splits(ticker: str, payload: list[dict[str, Any]], fetched_at: datetime,
                 raw_ref: str | None = None) -> list[CorporateAction]:
    """EODHD writes a split as 'new/old', e.g. '5.000000/1.000000' for a 1:5 split."""
    code = tickers.normalize(ticker)
    actions = []
    for row in payload:
        new, old = (Decimal(x) for x in row["split"].split("/"))
        actions.append(CorporateAction(
            ticker=code,
            action_type=ActionType.SPLIT if new > old else ActionType.REVERSE_SPLIT,
            ex_date=date.fromisoformat(row["date"]),
            ratio_old=old,
            ratio_new=new,
            source=SOURCE,
            fetched_at=fetched_at,
            raw_ref=raw_ref,
        ))
    return actions


def parse_dividends(ticker: str, payload: list[dict[str, Any]], fetched_at: datetime,
                    raw_ref: str | None = None) -> list[CorporateAction]:
    code = tickers.normalize(ticker)
    actions = []
    for row in payload:
        amount = _dec(row.get("unadjustedValue")) or _dec(row.get("value"))
        if amount is None:
            continue
        actions.append(CorporateAction(
            ticker=code,
            action_type=ActionType.CASH_DIVIDEND,
            ex_date=date.fromisoformat(row["date"]),
            cash_amount=amount,
            currency=row.get("currency") or "IDR",
            source=SOURCE,
            fetched_at=fetched_at,
            raw_ref=raw_ref,
        ))
    return actions


class EodhdProvider:
    source = SOURCE

    def __init__(self, api_token: str, raw_store: RawStore | None = None,
                 client: httpx.Client | None = None) -> None:
        self._token = api_token
        self._raw = raw_store
        self._client = client or httpx.Client(timeout=30.0)

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        params = {**params, "api_token": self._token, "fmt": "json"}
        response = self._client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise TypeError(f"Unexpected EODHD response for {path}: {str(data)[:200]}")
        return data

    def _fetch(self, kind: str, path: str, ticker: str, start: date, end: date):
        fetched_at = datetime.now(UTC)
        payload = self._get(path, {"from": start.isoformat(), "to": end.isoformat()})
        ref = self._raw.save(SOURCE, kind, tickers.normalize(ticker), payload, fetched_at) if self._raw else None
        return payload, fetched_at, ref

    def daily_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        payload, fetched_at, ref = self._fetch("eod", f"eod/{tickers.to_eodhd(ticker)}", ticker, start, end)
        return parse_eod(ticker, payload, fetched_at, ref)

    def corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateAction]:
        symbol = tickers.to_eodhd(ticker)
        splits, t1, r1 = self._fetch("splits", f"splits/{symbol}", ticker, start, end)
        divs, t2, r2 = self._fetch("dividends", f"div/{symbol}", ticker, start, end)
        return parse_splits(ticker, splits, t1, r1) + parse_dividends(ticker, divs, t2, r2)
