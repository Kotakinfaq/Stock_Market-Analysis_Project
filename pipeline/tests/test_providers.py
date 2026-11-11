"""Adapter parsing tests. The payloads are synthetic examples in each vendor's response shape,
not real market data."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from idx_pipeline.models import ActionType, PriceBasis
from idx_pipeline.providers import eodhd
from idx_pipeline.providers.yfinance_provider import bars_from_rows
from idx_pipeline.raw_store import RawStore

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def test_parse_eod_skips_empty_days():
    payload = [
        {"date": "2026-11-05", "open": 1000, "high": 1010, "low": 990, "close": 1005,
         "adjusted_close": 1005, "volume": 123400},
        {"date": "2026-11-06", "open": 0, "high": 0, "low": 0, "close": 0, "adjusted_close": 0, "volume": 0},
    ]
    bars = eodhd.parse_eod("AAAA.JK", payload, NOW)
    assert len(bars) == 1
    assert bars[0].ticker == "AAAA"
    assert bars[0].close == Decimal(1005)
    assert bars[0].volume_shares == 123400
    assert bars[0].source == "eodhd"


def test_parse_splits_and_dividends():
    splits = eodhd.parse_splits("AAAA", [{"date": "2021-10-13", "split": "5.000000/1.000000"},
                                         {"date": "2023-01-02", "split": "1.000000/10.000000"}], NOW)
    assert [s.action_type for s in splits] == [ActionType.SPLIT, ActionType.REVERSE_SPLIT]
    assert splits[0].ratio_old == Decimal("1.000000") and splits[0].ratio_new == Decimal("5.000000")

    divs = eodhd.parse_dividends("AAAA", [{"date": "2026-04-01", "value": 100, "unadjustedValue": 120,
                                           "currency": "IDR"}], NOW)
    assert divs[0].action_type is ActionType.CASH_DIVIDEND
    assert divs[0].cash_amount == Decimal(120)


def test_provider_calls_api_and_keeps_raw_file(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"date": "2026-11-06", "open": 1, "high": 1, "low": 1,
                                          "close": 1000, "volume": 5}])

    provider = eodhd.EodhdProvider("test-token", raw_store=RawStore(tmp_path),
                                   client=httpx.Client(transport=httpx.MockTransport(handler)))
    bars = provider.daily_prices("AAAA", date(2026, 11, 6), date(2026, 11, 6))
    assert "/api/eod/AAAA.JK" in seen["url"] and "from=2026-11-06" in seen["url"]
    raw_file = tmp_path / bars[0].raw_ref
    assert json.loads(raw_file.read_text())[0]["close"] == 1000


def test_yfinance_rows():
    rows = [(date(2026, 11, 6), {"Open": 1000.0, "High": 1010.0, "Low": 995.0, "Close": 1005.0,
                                 "Volume": 1000.0}),
            (date(2026, 11, 7), {"Open": float("nan"), "Close": float("nan"), "Volume": float("nan")})]
    bars = bars_from_rows("aaaa.jk", rows, NOW)
    assert len(bars) == 1
    assert bars[0].price_basis is PriceBasis.SPLIT_ADJUSTED
    assert bars[0].volume_shares == 1000
