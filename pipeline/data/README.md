# Pipeline data files

These are filled in by hand from official sources. The pipeline never guesses them.

## `kompas100/<period_start>.csv`

One file per Kompas100 review period, named by the date the period starts, e.g. `2026-08-01.csv`.
Copy each list from IDX's index announcement and **keep every past period**: backtests need the
members as they were on each date.

```csv
ticker
AAAA
BBBB
```

Codes without `.JK`. Then run `idx-pipeline sync-universe`.

## `ticker_names.csv` (optional)

```csv
ticker,name
AAAA,Example Company Tbk
```

## Holidays

Load IDX's official trading holidays into `market.holidays` each year (from the IDX announcement
listing exchange holidays). The trading calendar uses them to know which days should have prices.

## `raw/`

Every vendor response, saved exactly as received. Ignored by git; back it up to object storage.
