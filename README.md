# IDX Stock Analysis

AI-assisted research for Kompas100 stocks: rule-based scores plus short bilingual briefs for
long-term investors and swing traders.

**Status: Phase 0.** The database schema and the daily price pipeline with cross-source checks.

## Layout

| Folder | What it is |
|---|---|
| `supabase/migrations/` | The database schema, as plain SQL managed by the Supabase CLI |
| `pipeline/` | Python jobs: data adapters, ingestion, cross-source checks. Runs in Docker on the small server. |
| `web/` | The Next.js site (Phase 1) |

## How the data is organised

- `market.*` tables are written only by the pipeline and are never exposed through the Supabase API.
- `web.*` views are all the site can read. `web.daily_prices` only shows sources marked `display` in
  `market.source_license`. Today that's only `idx`, which becomes valid once the IDX licence is signed.
- Prices are stored raw (not dividend-adjusted), volume always in shares, tickers without `.JK`.
- Every vendor response is saved under `pipeline/data/raw/` so history can be rebuilt.

## Set up (works on an 8 GB Mac)

You don't need Docker or a local database. Use a free Supabase project as the development database.

1. Install `uv` (Python) and the Supabase CLI:
   ```bash
   brew install uv supabase/tap/supabase
   ```
2. Create a free Supabase project in the **Singapore** region, then link it and apply the schema:
   ```bash
   supabase link --project-ref <your-project-ref>
   ```
   ```bash
   supabase db push
   ```
3. Set up the pipeline:
   ```bash
   cd pipeline && uv sync && cp .env.example .env
   ```
   Fill in `DATABASE_URL` and `EODHD_API_TOKEN` in `.env`, then load them with `set -a; source .env; set +a`.
4. Add the current Kompas100 list as `pipeline/data/kompas100/<period_start>.csv` (see
   `pipeline/data/README.md`), then:
   ```bash
   uv run idx-pipeline sync-universe
   ```
5. Fetch a week of prices and compare sources:
   ```bash
   uv run idx-pipeline ingest-prices --source eodhd --start 2026-11-02 --end 2026-11-06
   ```
   ```bash
   uv sync --extra yfinance && uv run idx-pipeline ingest-prices --source yfinance --start 2026-11-02 --end 2026-11-06
   ```
   ```bash
   uv run idx-pipeline reconcile --date 2026-11-06 --a eodhd --b yfinance
   ```
   `reconcile` exits with code 2 when it finds problems, so a scheduler can alert on it.

## Tests

```bash
cd pipeline && uv run pytest
```

Database tests run only when `TEST_DATABASE_URL` points at a **throwaway** Postgres (they wipe the
schemas). CI runs them against a Postgres container.

## Things to verify before trusting the data

- **EODHD price basis and volume unit for `.JK`**: `providers/eodhd.py` assumes split-adjusted prices
  and volume in shares. The first `reconcile` runs will show a mismatch if either is wrong.
- **IDX tick sizes** in `ticks.py`: confirm against the current IDX trading rules.
- **Kompas100 lists and holidays** must come from official IDX announcements.

## Not in Phase 0 yet

Fundamentals adapter, news and disclosure feeds, the corporate-action adjustment engine, scores,
AI briefs, and the website.
