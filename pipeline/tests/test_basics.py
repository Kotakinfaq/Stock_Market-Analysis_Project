from datetime import date
from decimal import Decimal

import pytest

from idx_pipeline import calendar, tickers, ticks, units


@pytest.mark.parametrize("raw, expected", [("BBCA", "BBCA"), ("bbca.jk", "BBCA"), (" TLKM.JK ", "TLKM")])
def test_normalize(raw, expected):
    assert tickers.normalize(raw) == expected


@pytest.mark.parametrize("raw", ["", "BBC", "BBCA.SI", "BB-A"])
def test_normalize_rejects(raw):
    with pytest.raises(ValueError):
        tickers.normalize(raw)


def test_vendor_symbols():
    assert tickers.to_yahoo("bbca") == "BBCA.JK"
    assert tickers.to_eodhd("BBCA.JK") == "BBCA.JK"


def test_volume_units():
    assert units.to_shares(12, units.VolumeUnit.LOTS) == 1200
    assert units.to_shares(12, units.VolumeUnit.SHARES) == 12
    assert units.to_shares(None, units.VolumeUnit.LOTS) is None
    assert units.looks_like_lot_mismatch(1_000_000, 10_000)
    assert not units.looks_like_lot_mismatch(1_000_000, 990_000)


@pytest.mark.parametrize("price, tick", [(150, 1), (200, 2), (499, 2), (500, 5), (1995, 5),
                                         (2000, 10), (4990, 10), (5000, 25), (9750, 25)])
def test_tick_size(price, tick):
    assert ticks.tick_size(price) == Decimal(tick)


def test_round_to_tick():
    assert ticks.round_to_tick(9873) == Decimal(9875)
    assert ticks.round_to_tick(4996) == Decimal(5000)
    assert ticks.round_to_tick(1234) == Decimal(1235)
    assert ticks.is_valid_price(9750)
    assert not ticks.is_valid_price(9760)


def test_trading_days_skip_weekends_and_holidays():
    holidays = {date(2026, 11, 4)}
    days = list(calendar.trading_days(date(2026, 11, 2), date(2026, 11, 9), holidays))
    assert days == [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)]
