from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from idx_pipeline import reconcile, universe
from idx_pipeline.models import PriceBar, PriceBasis

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
DAY = date(2026, 11, 6)


def write_period(directory, start, codes):
    (directory / f"{start}.csv").write_text("ticker\n" + "\n".join(codes) + "\n", encoding="utf-8")


def test_members_on_uses_latest_period(tmp_path):
    write_period(tmp_path, "2026-02-01", ["AAAA", "BBBB"])
    write_period(tmp_path, "2026-08-01", ["AAAA", "CCCC"])
    periods = universe.load_periods(tmp_path)
    assert universe.members_on(date(2026, 3, 1), periods) == {"AAAA", "BBBB"}
    assert universe.members_on(date(2026, 8, 1), periods) == {"AAAA", "CCCC"}
    with pytest.raises(LookupError):
        universe.members_on(date(2026, 1, 1), periods)


def bar(ticker, close, source, volume=1_000_000):
    return PriceBar(ticker, DAY, None, None, None, Decimal(close), volume, source, PriceBasis.RAW, NOW)


def test_reconcile_flags_gap_missing_and_lot_mismatch():
    expected = frozenset({"AAAA", "BBBB", "CCCC", "DDDD"})
    a = [bar("AAAA", "1000", "a"), bar("BBBB", "2000", "a"), bar("DDDD", "500", "a", volume=10_000)]
    b = [bar("AAAA", "1003", "b"), bar("BBBB", "2050", "b"), bar("CCCC", "300", "b"), bar("DDDD", "500", "b")]
    issues = reconcile.compare(DAY, a, b, expected, "a", "b")
    found = {(i.ticker, i.issue) for i in issues}
    assert found == {("BBBB", "close_gap"), ("CCCC", "missing_in_a"), ("DDDD", "volume_unit")}
    gap = next(i for i in issues if i.issue == "close_gap")
    assert gap.diff_pct == Decimal("2.4390")


def test_reconcile_ignores_small_differences():
    expected = frozenset({"AAAA"})
    issues = reconcile.compare(DAY, [bar("AAAA", "1000", "a")], [bar("AAAA", "1004", "b")], expected, "a", "b")
    assert issues == []


def test_missing_tickers():
    assert reconcile.missing_tickers(DAY, [bar("AAAA", "1", "a")], frozenset({"AAAA", "BBBB"})) == ["BBBB"]
