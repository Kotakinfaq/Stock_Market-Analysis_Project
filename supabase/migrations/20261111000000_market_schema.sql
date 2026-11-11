-- Phase 0 schema: market data for Kompas100.
--
-- Layout
--   market.*  tables written only by the Python pipeline (never exposed through the Supabase API)
--   web.*     read-only views the Next.js site is allowed to read
--
-- Licence rule (Pillar 1): the site may only show rows whose source is licensed for display.
-- Which sources count as "display" lives in market.source_license, so buying the IDX licence
-- later is a data change, not a code change.

create schema if not exists market;
create schema if not exists web;

-- ---------------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------------

create type market.license_class as enum ('display', 'non_display', 'research');

create table market.source_license (
    source         text primary key,                -- e.g. 'eodhd', 'yfinance', 'idx'
    license_class  market.license_class not null,
    notes          text
);

insert into market.source_license (source, license_class, notes) values
    ('yfinance', 'research',    'Yahoo Finance API is for personal use only. Backfill and research only.'),
    ('eodhd',    'non_display', 'Personal plans prohibit display. Internal calculation and cross-checks only.'),
    ('idx',      'display',     'IDX end-of-day licence via a redistributor. Only valid once the licence is signed.');

create table market.tickers (
    ticker                 text primary key check (ticker ~ '^[A-Z0-9]{4}$'),  -- IDX code without .JK
    name                   text not null,
    sector_idxic           text,                    -- IDX Industrial Classification sector
    reporting_currency     char(3) not null default 'IDR',
    fiscal_year_end_month  smallint not null default 12 check (fiscal_year_end_month between 1 and 12),
    statement_template     text not null default 'general'
                           check (statement_template in ('general', 'bank', 'insurance', 'securities', 'multifinance')),
    is_active              boolean not null default true,
    updated_at             timestamptz not null default now()
);

-- Point-in-time index membership, so backtests use the list as it was on each date.
create table market.index_membership (
    index_code    text not null check (index_code in ('KOMPAS100', 'LQ45', 'IDX80')),
    ticker        text not null references market.tickers (ticker),
    period_start  date not null,
    period_end    date,                             -- null = current period
    source_ref    text,                             -- IDX announcement number or URL
    primary key (index_code, ticker, period_start),
    check (period_end is null or period_end >= period_start)
);

create table market.holidays (
    holiday_date  date primary key,
    description   text not null
);

-- ---------------------------------------------------------------------------
-- Prices and corporate actions (raw, never vendor-adjusted for dividends)
-- ---------------------------------------------------------------------------

create table market.prices_daily (
    ticker         text not null references market.tickers (ticker),
    trade_date     date not null,
    source         text not null references market.source_license (source),
    open           numeric(14, 2),
    high           numeric(14, 2),
    low            numeric(14, 2),
    close          numeric(14, 2) not null,
    volume_shares  bigint,                          -- always shares, never lots (1 lot = 100 shares)
    price_basis    text not null check (price_basis in ('raw', 'split_adjusted')),
    fetched_at     timestamptz not null,
    raw_ref        text,                            -- path of the raw file this row came from
    primary key (ticker, trade_date, source)
);

create index prices_daily_date_idx on market.prices_daily (trade_date);

create type market.corporate_action_type as enum
    ('split', 'reverse_split', 'bonus_shares', 'rights_issue', 'cash_dividend', 'stock_dividend');

create table market.corporate_actions (
    id            bigint generated always as identity primary key,
    ticker        text not null references market.tickers (ticker),
    action_type   market.corporate_action_type not null,
    ex_date       date not null,
    ratio_old     numeric,                          -- e.g. split 1:5 -> ratio_old 1, ratio_new 5
    ratio_new     numeric,
    cash_amount   numeric(14, 4),                   -- per share, for dividends
    currency      char(3),
    source        text not null references market.source_license (source),
    fetched_at    timestamptz not null,
    raw_ref       text,
    unique (ticker, action_type, ex_date, source)
);

-- ---------------------------------------------------------------------------
-- Operations
-- ---------------------------------------------------------------------------

create table market.run_log (
    id            bigint generated always as identity primary key,
    job           text not null,
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    status        text not null default 'running' check (status in ('running', 'ok', 'failed')),
    rows_written  integer,
    details       jsonb not null default '{}'::jsonb,
    error         text
);

create table market.reconciliation_issues (
    id            bigint generated always as identity primary key,
    trade_date    date not null,
    ticker        text not null,
    source_a      text not null,
    source_b      text not null,
    close_a       numeric(14, 2),
    close_b       numeric(14, 2),
    diff_pct      numeric(8, 4),
    issue         text not null check (issue in ('close_gap', 'missing_in_a', 'missing_in_b', 'volume_unit')),
    created_at    timestamptz not null default now(),
    unique (trade_date, ticker, source_a, source_b, issue)
);

-- ---------------------------------------------------------------------------
-- What the website may read
-- ---------------------------------------------------------------------------

create view web.daily_prices as
select p.ticker, p.trade_date, p.open, p.high, p.low, p.close, p.volume_shares, p.source
from market.prices_daily p
join market.source_license l on l.source = p.source
where l.license_class = 'display';

create view web.tickers as
select ticker, name, sector_idxic from market.tickers where is_active;

-- Read-only role for the Next.js site. Set its password by hand in the SQL editor
-- (never in a migration):  alter role web_reader with login password '...';
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'web_reader') then
        create role web_reader nologin;
    end if;
end $$;

revoke all on schema market from web_reader;
grant usage on schema web to web_reader;
grant select on all tables in schema web to web_reader;
alter default privileges in schema web grant select on tables to web_reader;
