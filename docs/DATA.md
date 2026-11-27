# Data guide

## Where the numbers come from

| Data | Source | How it gets in |
|---|---|---|
| Daily min / max / modal price per market, variety and grade | **AGMARKNET** (Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare), through the official **data.gov.in** API, GODL-India licence | `pipeline/sources/agmarknet.py`, cached in `data/raw/agmarknet/datagovin_cache.csv` |
| Arrival quantities | not in the data.gov.in resources | add an AGMARKNET export / scraper file to `data/raw/agmarknet/` (see below) |
| Rainfall, max temperature per market | Open-Meteo (ERA5 archive + recent days) | `pipeline/sources/weather.py`, cached in `data/raw/weather.csv` |
| Market coordinates | OpenStreetMap (Nominatim) | `data/catalog.json` |
| Markets, crops, aliases, crop calendar, pickup points | team-curated | `data/catalog.json` |
| Transport, commission, handling defaults | first estimates, to be replaced by the FPO cost survey | `data/catalog.json` → `defaults` (farmers can edit them in the app) |
| Assistant test questions | team-written (50, Telugu / romanised Telugu / English) | `data/assistant_eval.json` |

data.gov.in resources used:

- `35985678-0d79-46b4-9ed6-6f13308a1d24` — Variety-wise Daily Market Prices Data of Commodity (history from 2010)
- `9ef84268-d588-465a-a308-a864a43d0070` — Current Daily Price of Various Commodities from Various Markets (today)

The key lives only in the GitHub secret `DATA_GOV_IN_API_KEY` (and in your local environment when you run the
pipeline yourself). It is never stored in the repository.

## How the data is pulled

- **First run / `--history` / cache older than 30 days:** every Andhra Pradesh record for Tomato, Onion and Banana
  since 2022-01-01 (all AP markets are kept, so the market list can change without pulling again). The pipeline logs
  how many records the API reported and how many arrived, so a short pull is visible.
- **Every daily run (09:30 and 18:00 IST):** each of the last 10 days is re-read with an exact date filter (late
  uploads and corrections land), plus today's file from the current-price resource.
- "Banana - Green" (raw cooking banana) is a different product and is not mixed with Banana.
- Each day is read once **for all Andhra Pradesh crops** (one request per day). Rows for the 45 optional crops in
  `catalog.json → extra_crops` are kept for the last 120 days in `data/raw/agmarknet/datagovin_extra.csv`
  (a 45-day backfill on first run) and summarised in `data/processed/extra_prices.json`: the latest price per market
  (median of the varieties reported that day), min–max, varieties and a 30-day history. Prices only, no forecasts.
  Coconut and non-farm items are left out (different price units).

## How markets were chosen

From the cache, for each crop and market: days reported in the last 3 years, last report date, and variety mix.
A market is in the app if it reported in the last 7 days. It gets its **own backtested forecast** if it has enough
history in both the calibration and the test window; newer markets (reporting since 2025–26) get the crop's pooled
model, always marked low confidence. Two markets were renamed in AGMARKNET and are joined into one series after
checking the price level stays consistent: Vayalapadu → Valmikipuram APMC (tomato) and Ravulapelem → Ravulapalem
(Kothapeta APMC) (banana). Old "Tirupati" banana records (around ₹9,000, a different unit from its successor
Thiruchanur at around ₹1,600) are not joined. "Guramkonda Sub-yard of AMC Valmikipuram" publishes the same numbers as
Valmikipuram (identical on 169 of 174 days), so it is not a separate market; farmers asking about Gurramkonda get
Valmikipuram's price.

## What the Data Agent does on every run

- Matches each record to a PoC market using the exact AGMARKNET names in `data_names` (with or without "APMC");
  farmer phrasings in `aliases` are only used by the assistant.
- Converts per-kg prices to per-quintal (whole files by column name, single rows by comparing with the local median).
- Removes duplicate submissions (the API repeats some onion records).
- Builds **one consistent price per market and day**: the variety reported on at least 75% of days (then its main
  grade) where a market lists several lots a day; the daily median of the varieties reported every day when there are
  several (Ravulapalem: 6 banana varieties); the single daily record where a market reports one price a day under
  changing labels; otherwise the daily median. Today's price for every variety is kept for the detail page.
- Treats **15 or more identical prices in a row** as a feed that stopped updating: the repeats are left out of the
  series, and a market still repeating today is shown as "not changing at the source since <date>" with no forecast
  (Kuppam since 18 Aug 2026). Zero min/max values are replaced by the modal and counted.
- Flags impossible values (max below min, modal outside min–max, price more than 2.2× away from the median of the
  same variety and grade at that market).
  **Flagged rows are held back until an admin accepts them** in the Admin screen (or in `data/reviews.json`).
- Reports missing days per series (never filled in), weekly closing days (read from the data), freshness and history
  length.

## Adding AGMARKNET exports or scraper output (adds arrivals)

1. Put one or more `.csv` or `.xlsx` files in `data/raw/agmarknet/` (any file name).
2. Columns are matched by name, so exports from the old portal, AGMARKNET 2.0, the OGD API and most scrapers work as
   they are. Needed: a date column (`Arrival_Date`, `Price Date`, `Reported Date` or `date`), market, commodity and modal
   price. Optional: state, district, variety, grade, min price, max price, arrivals.
   - Prices in Rs/quintal (a column name containing `kg` is converted ×100).
   - Arrivals in tonnes (a column name containing `qtl`/`quintal` is converted ÷10).
   - Dates can be `03/11/2026`, `2026-11-03` or `03 Nov 2026`.
3. Run `python -m pipeline.run --source real` (or push to GitHub and let the daily workflow run).

Minimal example:

```csv
State,District,Market,Commodity,Variety,Grade,Arrival_Date,Min_Price,Max_Price,Modal_Price,Arrivals_Tonnes
Andhra Pradesh,Annamayya,Madanapalli APMC,Tomato,Local,FAQ,03/11/2026,1300,2600,1900,820.5
```
