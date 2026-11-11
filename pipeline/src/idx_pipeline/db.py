"""Postgres access for the pipeline. Only this module writes SQL."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from .models import CorporateAction, PriceBar, PriceBasis
from .reconcile import Issue
from .universe import Period


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=False)


def upsert_prices(conn: psycopg.Connection, bars: Iterable[PriceBar]) -> int:
    rows = [(b.ticker, b.trade_date, b.source, b.open, b.high, b.low, b.close, b.volume_shares,
             b.price_basis.value, b.fetched_at, b.raw_ref) for b in bars]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into market.prices_daily
                (ticker, trade_date, source, open, high, low, close, volume_shares,
                 price_basis, fetched_at, raw_ref)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (ticker, trade_date, source) do update set
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume_shares = excluded.volume_shares,
                price_basis = excluded.price_basis, fetched_at = excluded.fetched_at,
                raw_ref = excluded.raw_ref
            """,
            rows,
        )
    return len(rows)


def upsert_corporate_actions(conn: psycopg.Connection, actions: Iterable[CorporateAction]) -> int:
    rows = [(a.ticker, a.action_type.value, a.ex_date, a.ratio_old, a.ratio_new, a.cash_amount,
             a.currency, a.source, a.fetched_at, a.raw_ref) for a in actions]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into market.corporate_actions
                (ticker, action_type, ex_date, ratio_old, ratio_new, cash_amount,
                 currency, source, fetched_at, raw_ref)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (ticker, action_type, ex_date, source) do update set
                ratio_old = excluded.ratio_old, ratio_new = excluded.ratio_new,
                cash_amount = excluded.cash_amount, currency = excluded.currency,
                fetched_at = excluded.fetched_at, raw_ref = excluded.raw_ref
            """,
            rows,
        )
    return len(rows)


def sync_membership(conn: psycopg.Connection, index_code: str, periods: list[Period],
                    names: dict[str, str]) -> int:
    """Upsert tickers and point-in-time membership. A period ends the day before the next one starts."""
    ordered = sorted(periods, key=lambda p: p.start)
    with conn.cursor() as cur:
        all_tickers = sorted(set().union(*(p.members for p in ordered)))
        cur.executemany(
            """
            insert into market.tickers (ticker, name) values (%s, %s)
            on conflict (ticker) do update set name = excluded.name, updated_at = now()
            where market.tickers.name = market.tickers.ticker  -- only replace placeholder names
            """,
            [(t, names.get(t, t)) for t in all_tickers],
        )
        count = 0
        for i, period in enumerate(ordered):
            end = None
            if i + 1 < len(ordered):
                end = date.fromordinal(ordered[i + 1].start.toordinal() - 1)
            cur.executemany(
                """
                insert into market.index_membership (index_code, ticker, period_start, period_end)
                values (%s, %s, %s, %s)
                on conflict (index_code, ticker, period_start) do update set period_end = excluded.period_end
                """,
                [(index_code, t, period.start, end) for t in sorted(period.members)],
            )
            count += len(period.members)
    return count


def load_prices(conn: psycopg.Connection, source: str, trade_date: date) -> list[PriceBar]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select ticker, trade_date, open, high, low, close, volume_shares, source, price_basis,
                   fetched_at, raw_ref
            from market.prices_daily where source = %s and trade_date = %s
            """,
            (source, trade_date),
        )
        return [PriceBar(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], PriceBasis(r[8]), r[9], r[10])
                for r in cur.fetchall()]


def save_issues(conn: psycopg.Connection, issues: Iterable[Issue]) -> int:
    rows = [(i.trade_date, i.ticker, i.source_a, i.source_b, i.close_a, i.close_b, i.diff_pct, i.issue)
            for i in issues]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into market.reconciliation_issues
                (trade_date, ticker, source_a, source_b, close_a, close_b, diff_pct, issue)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (trade_date, ticker, source_a, source_b, issue) do update set
                close_a = excluded.close_a, close_b = excluded.close_b, diff_pct = excluded.diff_pct
            """,
            rows,
        )
    return len(rows)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, Decimal)):
        return str(value)
    raise TypeError(type(value))


@contextmanager
def run_log(conn: psycopg.Connection, job: str, details: dict[str, Any] | None = None) -> Iterator[dict]:
    """Record a job run. The caller sets state['rows_written'] and may add to state['details']."""
    state: dict[str, Any] = {"rows_written": 0, "details": dict(details or {})}
    with conn.cursor() as cur:
        cur.execute("insert into market.run_log (job, details) values (%s, %s) returning id",
                    (job, json.dumps(state["details"], default=_json_default)))
        run_id = cur.fetchone()[0]
    conn.commit()
    try:
        yield state
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "update market.run_log set status = 'failed', finished_at = now(), error = %s, details = %s "
                "where id = %s",
                (f"{type(exc).__name__}: {exc}"[:2000], json.dumps(state["details"], default=_json_default),
                 run_id),
            )
        conn.commit()
        raise
    else:
        with conn.cursor() as cur:
            cur.execute(
                "update market.run_log set status = 'ok', finished_at = now(), rows_written = %s, "
                "details = %s where id = %s",
                (state["rows_written"], json.dumps(state["details"], default=_json_default), run_id),
            )
        conn.commit()
