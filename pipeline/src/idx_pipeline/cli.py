"""Command line entry point.

  idx-pipeline sync-universe
  idx-pipeline ingest-prices --source eodhd --start 2026-11-02 --end 2026-11-06
  idx-pipeline ingest-actions --start 2016-01-01 --end 2026-11-06
  idx-pipeline reconcile --date 2026-11-06 --a eodhd --b yfinance

Settings come from environment variables (see .env.example):
  DATABASE_URL, EODHD_API_TOKEN, RAW_DATA_DIR (default ./data/raw), UNIVERSE_DIR (default ./data/kompas100),
  TICKER_NAMES_FILE (default ./data/ticker_names.csv, optional, columns: ticker,name)
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import db, reconcile, universe
from .raw_store import RawStore

log = logging.getLogger("idx_pipeline")


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        sys.exit(f"Missing environment variable {name}. See .env.example.")
    return value


def _universe_dir() -> Path:
    return Path(_env("UNIVERSE_DIR", "data/kompas100"))


def _price_provider(source: str):
    raw = RawStore(Path(_env("RAW_DATA_DIR", "data/raw")))
    if source == "eodhd":
        from .providers.eodhd import EodhdProvider
        return EodhdProvider(_env("EODHD_API_TOKEN"), raw_store=raw)
    if source == "yfinance":
        from .providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    sys.exit(f"Unknown source {source!r}. Use eodhd or yfinance.")


def _tickers_for(args, periods: list[universe.Period]) -> list[str]:
    if args.tickers:
        from .tickers import normalize
        return sorted({normalize(t) for t in args.tickers.split(",")})
    # every stock that was a member at any point in the range, so history is complete
    members: set[str] = set()
    for p in periods:
        if p.start <= args.end:
            members |= p.members
    return sorted(members)


def cmd_sync_universe(args) -> None:
    periods = universe.load_periods(_universe_dir())
    names: dict[str, str] = {}
    names_file = Path(_env("TICKER_NAMES_FILE", "data/ticker_names.csv"))
    if names_file.exists():
        with names_file.open(newline="", encoding="utf-8") as f:
            names = {row["ticker"]: row["name"] for row in csv.DictReader(f)}
    with db.connect(_env("DATABASE_URL")) as conn, db.run_log(conn, "sync_universe") as state:
        state["rows_written"] = db.sync_membership(conn, "KOMPAS100", periods, names)
        state["details"]["periods"] = len(periods)
        conn.commit()
    log.info("Synced %d periods", len(periods))


def cmd_ingest_prices(args) -> None:
    provider = _price_provider(args.source)
    periods = universe.load_periods(_universe_dir())
    codes = _tickers_for(args, periods)
    failed: list[str] = []
    with db.connect(_env("DATABASE_URL")) as conn, db.run_log(
        conn, "ingest_prices", {"source": args.source, "start": args.start, "end": args.end}
    ) as state:
        for code in codes:
            try:
                bars = provider.daily_prices(code, args.start, args.end)
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the run
                log.warning("%s: %s", code, exc)
                failed.append(code)
                continue
            state["rows_written"] += db.upsert_prices(conn, bars)
            conn.commit()
        state["details"]["failed"] = failed
    log.info("Wrote %d rows for %d tickers; %d failed", state["rows_written"], len(codes), len(failed))
    if failed:
        sys.exit(1)


def cmd_ingest_actions(args) -> None:
    from .providers.eodhd import EodhdProvider
    provider = EodhdProvider(_env("EODHD_API_TOKEN"), raw_store=RawStore(Path(_env("RAW_DATA_DIR", "data/raw"))))
    codes = _tickers_for(args, universe.load_periods(_universe_dir()))
    with db.connect(_env("DATABASE_URL")) as conn, db.run_log(
        conn, "ingest_actions", {"start": args.start, "end": args.end}
    ) as state:
        for code in codes:
            state["rows_written"] += db.upsert_corporate_actions(
                conn, provider.corporate_actions(code, args.start, args.end))
            conn.commit()


def cmd_reconcile(args) -> None:
    periods = universe.load_periods(_universe_dir())
    expected = universe.members_on(args.date, periods)
    with db.connect(_env("DATABASE_URL")) as conn, db.run_log(
        conn, "reconcile", {"date": args.date, "a": args.a, "b": args.b}
    ) as state:
        issues = reconcile.compare(
            args.date, db.load_prices(conn, args.a, args.date), db.load_prices(conn, args.b, args.date),
            expected, args.a, args.b,
        )
        state["rows_written"] = db.save_issues(conn, issues)
        state["details"]["issues"] = len(issues)
        conn.commit()
    for issue in issues:
        log.warning("%s %s %s (a=%s b=%s diff=%s%%)", issue.trade_date, issue.ticker, issue.issue,
                    issue.close_a, issue.close_b, issue.diff_pct)
    log.info("%d issues for %d expected tickers", len(issues), len(expected))
    if issues:
        sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="idx-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync-universe", help="Load Kompas100 membership CSVs into the database")

    for name, helptext in (("ingest-prices", "Fetch daily prices"), ("ingest-actions", "Fetch splits and dividends")):
        p = sub.add_parser(name, help=helptext)
        if name == "ingest-prices":
            p.add_argument("--source", choices=["eodhd", "yfinance"], required=True)
        p.add_argument("--start", type=date.fromisoformat, required=True)
        p.add_argument("--end", type=date.fromisoformat, required=True)
        p.add_argument("--tickers", help="Comma-separated codes, e.g. BBCA,TLKM. Default: Kompas100 members.")

    p = sub.add_parser("reconcile", help="Compare one day's closes from two sources")
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--a", default="eodhd")
    p.add_argument("--b", default="yfinance")
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    handlers = {
        "sync-universe": cmd_sync_universe,
        "ingest-prices": cmd_ingest_prices,
        "ingest-actions": cmd_ingest_actions,
        "reconcile": cmd_reconcile,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
