# Data guide

## Where the numbers come from

| Data | Source | How it gets in |
|---|---|---|
| Daily min / max / modal price, arrivals | AGMARKNET | CSV/XLSX exports or scraper output in `data/raw/agmarknet/`, and/or the data.gov.in OGD API (`DATA_GOV_IN_API_KEY`) |
| Rainfall, max temperature per market | Open-Meteo (ERA5 archive + recent days) | fetched automatically, cached in `data/raw/weather.csv` |
| Markets, crops, aliases, crop calendar, pickup points | team-curated | `data/catalog.json` |
| Transport, commission, handling defaults | first estimates, to be replaced by the FPO cost survey | `data/catalog.json` → `defaults` (farmers can edit them in the app) |
| Assistant test questions | team-written (50, Telugu / romanised Telugu / English) | `data/assistant_eval.json` |

If no real price file is present, the pipeline generates a **simulated** dataset in AGMARKNET format so every
screen and model can be demonstrated. The app then shows a "Sample data" banner and every source label says
"simulated". As soon as a real file is added, the next run uses only real data and the banner disappears.

## Adding the scraped / exported AGMARKNET data

1. Put one or more `.csv` or `.xlsx` files in `data/raw/agmarknet/` (any file name, any number of files).
2. Columns are matched by name, so exports from the old portal, AGMARKNET 2.0, the OGD API and most scrapers work
   as they are. Needed: a date column (`Arrival_Date`, `Price Date`, `Reported Date` or `date`), market, commodity
   and modal price. Optional: state, district, variety, min price, max price, arrivals.
   - Prices in Rs/quintal (a column name containing `kg` is converted ×100).
   - Arrivals in tonnes (a column name containing `qtl`/`quintal` is converted ÷10).
   - Dates can be `03/11/2026`, `2026-11-03` or `03 Nov 2026`.
3. Run `python -m pipeline.run --source real` (or push to GitHub and let the daily workflow run).

Minimal example:

```csv
State,District,Market,Commodity,Variety,Arrival_Date,Min_Price,Max_Price,Modal_Price,Arrivals_Tonnes
Andhra Pradesh,Annamayya,Madanapalle,Tomato,Local,03/11/2026,1300,2600,1900,820.5
```

## What the Data Agent does on every run

- Matches spelling variants of markets and crops (`Madanapalli`, `TOMATO`, `Cuddapah` …) through the alias table
  and fuzzy matching; rows outside the PoC cluster are counted and dropped.
- Converts per-kg prices to per-quintal (whole files by column name, single rows by comparing with the local median).
- Removes duplicate submissions; combines several varieties on one day into one row (median modal, min of min, max of max, summed arrivals).
- Flags impossible values (max below min, modal outside min–max, price more than 2.2× away from the local median).
  **Flagged rows are held back until an admin accepts them** in the Admin screen (or in `data/reviews.json`).
- Reports missing days per series (not filled), freshness, and history length.

## Getting a data.gov.in key (optional)

Register at <https://data.gov.in>, copy the API key from *My Account*, and add it as the GitHub secret
`DATA_GOV_IN_API_KEY`. Run the *Daily data pipeline* workflow once with **history** ticked to pull past data.
Note: the OGD price resources do not include arrivals, so arrivals still need the AGMARKNET export.
