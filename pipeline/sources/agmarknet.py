"""Real AGMARKNET data: (1) CSV exports / scraper output dropped in data/raw/agmarknet/,
(2) the official data.gov.in OGD API when DATA_GOV_IN_API_KEY is set.

Both are turned into one raw schema:
    state, district, market_raw, commodity_raw, variety, date, min, max, modal, arrivals_t, price_unit, source
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import requests

from pipeline.common import RAW, RunLog

CSV_DIR = RAW / "agmarknet"
OGD_BASE = "https://api.data.gov.in/resource/"
OGD_HISTORY = "35985678-0d79-46b4-9ed6-6f13308a1d24"  # Variety-wise daily market prices (historical)
OGD_CURRENT = "9ef84268-d588-465a-a308-a864a43d0070"  # Current daily price of commodities (today)
RAW_COLS = ["state", "district", "market_raw", "commodity_raw", "variety", "date", "min", "max", "modal",
            "arrivals_t", "price_unit", "source"]


def _key(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _find(cols: dict[str, str], *preds) -> str | None:
    for k, original in cols.items():
        if all(p(k) for p in preds):
            return original
    return None


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map any AGMARKNET-style export (old portal, 2.0 portal, OGD API, scraper) to the raw schema."""
    cols = {_key(c): c for c in df.columns}
    c_date = (_find(cols, lambda k: "arrivaldate" in k) or _find(cols, lambda k: "reporteddate" in k)
              or _find(cols, lambda k: "pricedate" in k) or _find(cols, lambda k: "reportdate" in k)
              or _find(cols, lambda k: k in ("date", "tradedate")))
    c_market = (_find(cols, lambda k: k in ("market", "marketname", "marketcenter", "mandi", "apmc", "mandiname"))
                or _find(cols, lambda k: "market" in k and "code" not in k and "id" != k[-2:]))
    c_comm = _find(cols, lambda k: k in ("commodity", "commodityname", "crop", "cropname")) or _find(cols, lambda k: "commodity" in k and "code" not in k and "group" not in k)
    c_var = _find(cols, lambda k: k.startswith("variety"))
    c_state = _find(cols, lambda k: k in ("state", "statename"))
    c_dist = _find(cols, lambda k: k in ("district", "districtname"))
    c_min = _find(cols, lambda k: "min" in k and "price" in k)
    c_max = _find(cols, lambda k: "max" in k and "price" in k)
    c_modal = _find(cols, lambda k: "modal" in k)
    c_arr = _find(cols, lambda k: "arrival" in k and "date" not in k)
    missing = [n for n, c in [("date", c_date), ("market", c_market), ("commodity", c_comm), ("modal price", c_modal)] if c is None]
    if missing:
        raise ValueError(f"cannot find columns {missing} in {list(df.columns)}")

    out = pd.DataFrame({
        "state": df[c_state] if c_state else None,
        "district": df[c_dist] if c_dist else None,
        "market_raw": df[c_market],
        "commodity_raw": df[c_comm],
        "variety": df[c_var] if c_var else None,
        "date": pd.to_datetime(df[c_date].astype(str).str.strip(), dayfirst=True, errors="coerce", format="mixed"),
        "min": pd.to_numeric(df[c_min], errors="coerce") if c_min else None,
        "max": pd.to_numeric(df[c_max], errors="coerce") if c_max else None,
        "modal": pd.to_numeric(df[c_modal], errors="coerce"),
        "arrivals_t": pd.to_numeric(df[c_arr], errors="coerce") if c_arr else None,
    })
    price_col_text = _key(c_modal)
    out["price_unit"] = "kg" if ("kg" in price_col_text and "quintal" not in price_col_text) else "quintal"
    if c_arr and any(t in _key(c_arr) for t in ("qtl", "quintal")):
        out["arrivals_t"] = out["arrivals_t"] / 10.0
    return out


def load_csv_exports(log: RunLog) -> pd.DataFrame:
    frames = []
    for path in sorted(list(CSV_DIR.glob("*.csv")) + list(CSV_DIR.glob("*.xlsx"))):
        if path.name.startswith("datagovin_"):
            continue
        try:
            df = pd.read_excel(path) if path.suffix == ".xlsx" else pd.read_csv(path, low_memory=False)
            mapped = map_columns(df)
            mapped["source"] = "AGMARKNET"
            frames.append(mapped)
            log.add("data_agent", "load_csv", f"{path.name}: {len(mapped)} rows")
        except Exception as exc:
            log.add("data_agent", "load_csv", f"{path.name}: skipped ({exc})", level="warning")
    return pd.concat(frames, ignore_index=True)[RAW_COLS] if frames else pd.DataFrame(columns=RAW_COLS)


OGD_COMMODITIES = {"tomato": ["Tomato"], "onion": ["Onion"], "banana": ["Banana", "Banana - Green"]}


def _ogd_get(resource: str, key: str, filters: dict, limit: int, offset: int) -> dict:
    params = {"api-key": key, "format": "json", "limit": limit, "offset": offset}
    params.update({f"filters[{k}]": v for k, v in filters.items()})
    r = requests.get(OGD_BASE + resource, params=params, timeout=90, headers={"User-Agent": "MandiMitra-pipeline/1.0"})
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        raise RuntimeError(f"non-JSON reply ({r.status_code})")
    if r.status_code >= 400 or str(data.get("status", "")).lower() == "error" or data.get("error"):
        raise RuntimeError(f"data.gov.in said: {data.get('message') or data.get('error') or r.status_code}")
    return data


def _ogd_pages(resource: str, key: str, filters: dict, limit: int = 1000, max_pages: int = 300):
    """Page through a resource. Stops on an empty page, at `total`, or if the API repeats a page."""
    offset, first_prev = 0, None
    for _ in range(max_pages):
        data = _ogd_get(resource, key, filters, limit, offset)
        records = data.get("records") or []
        if not records or records[0] == first_prev:
            return
        first_prev = records[0]
        yield records
        offset += len(records)
        total = data.get("total")
        if total is not None and offset >= int(total):
            return


def _ogd_pull(resource: str, key: str, variants: list[dict]) -> tuple[list[pd.DataFrame], dict | None]:
    """Try filter spellings in turn (field names differ between resources); keep the first that returns rows."""
    for filters in variants:
        frames = [pd.DataFrame(page) for page in _ogd_pages(resource, key, filters)]
        if frames:
            return frames, filters
    return [], None


def fetch_datagovin(catalog: dict, log: RunLog, history: bool) -> pd.DataFrame:
    """Official OGD API (needs DATA_GOV_IN_API_KEY).

    History (all Andhra Pradesh markets for each crop; name matching keeps our cluster) is pulled on the
    first run, with --history, or when the cache is more than 3 days old. Other runs add the current-day file.
    """
    key = os.environ.get("DATA_GOV_IN_API_KEY", "").strip()
    cache = CSV_DIR / "datagovin_cache.csv"
    old = pd.read_csv(cache, parse_dates=["date"]) if cache.exists() else pd.DataFrame(columns=RAW_COLS)
    if not key:
        return old[RAW_COLS] if not old.empty else pd.DataFrame(columns=RAW_COLS)
    stale = old.empty or (pd.Timestamp.now().normalize() - old["date"].max()).days > 3
    state = catalog["state"]
    frames = []
    try:
        if history or stale:
            for crop in catalog["crops"]:
                for name in OGD_COMMODITIES.get(crop["id"], [crop["en"]]):
                    got, used = _ogd_pull(OGD_HISTORY, key, [
                        {"State": state, "Commodity": name},
                        {"State.keyword": state, "Commodity.keyword": name},
                        {"state": state, "commodity": name},
                    ])
                    frames += got
                    log.add("data_agent", "fetch_agmarknet",
                            f"data.gov.in history {name}: {sum(len(f) for f in got)} records" + (f" (filters {list(used)})" if used else ""))
        got, used = _ogd_pull(OGD_CURRENT, key, [{"state.keyword": state}, {"state": state}, {"State": state}])
        frames += got
        log.add("data_agent", "fetch_agmarknet", f"data.gov.in current-day file for {state}: {sum(len(f) for f in got)} records")
    except Exception as exc:
        log.add("data_agent", "fetch_agmarknet", f"data.gov.in fetch failed: {exc}", level="warning")
    if frames:
        new = map_columns(pd.concat(frames, ignore_index=True))
        new["source"] = "AGMARKNET"
        allr = pd.concat([old, new[RAW_COLS]], ignore_index=True)
        allr = allr.drop_duplicates(subset=["market_raw", "commodity_raw", "variety", "date"], keep="last")
        cache.parent.mkdir(parents=True, exist_ok=True)
        allr.to_csv(cache, index=False)
        return allr[RAW_COLS]
    return old[RAW_COLS] if not old.empty else pd.DataFrame(columns=RAW_COLS)


def load_real(catalog: dict, log: RunLog, history: bool = False) -> pd.DataFrame:
    parts = [load_csv_exports(log), fetch_datagovin(catalog, log, history)]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=RAW_COLS)
