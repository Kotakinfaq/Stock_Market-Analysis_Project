"""Integration tests against a real Postgres. Skipped unless TEST_DATABASE_URL is set.

The test wipes the market and web schemas in that database and re-applies the migrations,
so point it at a throwaway database, never at Supabase.
"""

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from idx_pipeline import db
from idx_pipeline.models import ActionType, CorporateAction, PriceBar, PriceBasis
from idx_pipeline.reconcile import compare
from idx_pipeline.universe import Period

URL = os.environ.get("TEST_DATABASE_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
DAY = date(2026, 11, 6)

pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute("drop schema if exists web cascade; drop schema if exists market cascade;")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            admin.execute(path.read_text())
    with db.connect(URL) as c:
        yield c


def bar(ticker, close, source, volume=1000):
    return PriceBar(ticker, DAY, None, None, None, Decimal(close), volume, source, PriceBasis.RAW, NOW)


def test_membership_prices_and_licence_view(conn):
    periods = [Period(date(2026, 2, 1), frozenset({"AAAA", "BBBB"})),
               Period(date(2026, 8, 1), frozenset({"AAAA", "CCCC"}))]
    assert db.sync_membership(conn, "KOMPAS100", periods, {"AAAA": "Alpha Tbk"}) == 4
    conn.commit()
    rows = conn.execute("select ticker, period_start, period_end from market.index_membership "
                        "where ticker = 'BBBB'").fetchall()
    assert rows == [("BBBB", date(2026, 2, 1), date(2026, 7, 31))]

    assert db.upsert_prices(conn, [bar("AAAA", "1000", "eodhd"), bar("AAAA", "1001", "yfinance")]) == 2
    assert db.upsert_prices(conn, [bar("AAAA", "1002", "eodhd")]) == 1  # re-run updates, no duplicate
    conn.commit()
    assert [b.close for b in db.load_prices(conn, "eodhd", DAY)] == [Decimal("1002.00")]

    # Neither eodhd nor yfinance is licensed for display, so the site sees nothing yet.
    assert conn.execute("select count(*) from web.daily_prices").fetchone()[0] == 0
    db.upsert_prices(conn, [bar("AAAA", "1003", "idx")])
    conn.commit()
    assert conn.execute("select source, close from web.daily_prices").fetchall() == [("idx", Decimal("1003.00"))]


def test_corporate_actions_issues_and_run_log(conn):
    db.sync_membership(conn, "KOMPAS100", [Period(date(2026, 2, 1), frozenset({"AAAA"}))], {})
    action = CorporateAction("AAAA", ActionType.SPLIT, date(2026, 5, 4), "eodhd", NOW,
                             ratio_old=Decimal(1), ratio_new=Decimal(5))
    assert db.upsert_corporate_actions(conn, [action, action]) == 2  # idempotent upsert
    assert conn.execute("select count(*) from market.corporate_actions").fetchone()[0] == 1

    issues = compare(DAY, [bar("AAAA", "1000", "eodhd")], [bar("AAAA", "1100", "yfinance")],
                     frozenset({"AAAA"}), "eodhd", "yfinance")
    with db.run_log(conn, "reconcile", {"date": DAY}) as state:
        state["rows_written"] = db.save_issues(conn, issues)
        conn.commit()
    assert conn.execute("select status, rows_written from market.run_log").fetchone() == ("ok", 1)

    with pytest.raises(RuntimeError), db.run_log(conn, "broken"):
        raise RuntimeError("boom")
    status, error = conn.execute(
        "select status, error from market.run_log where job = 'broken'").fetchone()
    assert status == "failed" and "boom" in error


def test_web_reader_cannot_read_market_tables(conn):
    conn.execute("set role web_reader")
    assert conn.execute("select count(*) from web.tickers").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("select * from market.prices_daily")
