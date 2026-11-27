"""Real AGMARKNET data: (1) CSV exports / scraper output dropped in data/raw/agmarknet/,
(2) the official data.gov.in OGD API when DATA_GOV_IN_API_KEY is set.

Both are turned into one raw schema:
    state, district, market_raw, commodity_raw, variety, grade, date, min, max, modal, arrivals_t, price_unit, source

OGD resources used (Ministry of Agriculture & Farmers Welfare, AGMARKNET):
- 35985678-0d79-46b4-9ed6-6f13308a1d24  Variety-wise Daily Market Prices Data of Commodity (history, from 2010)
- 9ef84268-d588-465a-a308-a864a43d0070  Current Daily Price of Various Commodities from Various Markets (today)
Neither resource carries arrival quantities.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

import pandas as pd
import requests

from pipeline.common import RAW, RunLog

CSV_DIR = RAW / "agmarknet"
CACHE = CSV_DIR / "datagovin_cache.csv"
EXTRA_CACHE = CSV_DIR / "datagovin_extra.csv"   # optional crops a farmer can add (prices only)
EXTRA_BACKFILL_DAYS = 45
EXTRA_KEEP_DAYS = 120
OGD_BASE = "https://api.data.gov.in/resource/"
OGD_HISTORY = "35985678-0d79-46b4-9ed6-6f13308a1d24"
OGD_CURRENT = "9ef84268-d588-465a-a308-a864a43d0070"
RAW_COLS = ["state", "district", "market_raw", "commodity_raw", "variety", "grade", "date", "min", "max", "modal",
            "arrivals_t", "price_unit", "source"]
HISTORY_START = "2022-01-01"        # older years are not needed for a 3-year PoC and would bloat the cache
REFRESH_DAYS = 10                   # daily runs re-read the last 10 days, so late uploads and corrections land
# "Banana - Green" is raw (cooking) banana, a different product with different prices; it is not mixed in.
OGD_COMMODITIES = {"tomato": ["Tomato"], "onion": ["Onion"], "banana": ["Banana"]}


def _key(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _find(cols: dict[str, str], *preds) -> str | None:
    for k, original in cols.items():
        if all(p(k) for p in preds):
            return original
    return None


def _dates(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    out = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    rest = out.isna()
    if rest.any():
        out[rest] = pd.to_datetime(s[rest], dayfirst=True, errors="coerce", format="mixed")
    return out


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map any AGMARKNET-style export (old portal, 2.0 portal, OGD API, scraper) to the raw schema."""
    cols = {_key(c): c for c in df.columns}
    c_date = (_find(cols, lambda k: "arrivaldate" in k) or _find(cols, lambda k: "reporteddate" in k)
              or _find(cols, lambda k: "pricedate" in k) or _find(cols, lambda k: "reportdate" in k)
              or _find(cols, lambda k: k in ("date", "tradedate")))
    c_market = (_find(cols, lambda k: k in ("market", "marketname", "marketcenter", "mandi", "apmc", "mandiname", "marketraw"))
                or _find(cols, lambda k: "market" in k and "code" not in k and "id" != k[-2:]))
    c_comm = (_find(cols, lambda k: k in ("commodity", "commodityname", "crop", "cropname", "commodityraw"))
              or _find(cols, lambda k: "commodity" in k and "code" not in k and "group" not in k))
    c_var = _find(cols, lambda k: k.startswith("variety"))
    c_grade = _find(cols, lambda k: k.startswith("grade"))
    c_state = _find(cols, lambda k: k in ("state", "statename"))
    c_dist = _find(cols, lambda k: k in ("district", "districtname"))
    c_min = _find(cols, lambda k: "min" in k and "price" in k) or _find(cols, lambda k: k == "min")
    c_max = _find(cols, lambda k: "max" in k and "price" in k) or _find(cols, lambda k: k == "max")
    c_modal = _find(cols, lambda k: "modal" in k)
    c_arr = _find(cols, lambda k: "arrival" in k and "date" not in k)
    missing = [n for n, c in [("date", c_date), ("market", c_market), ("commodity", c_comm), ("modal price", c_modal)] if c is None]
    if missing:
        raise ValueError(f"cannot find columns {missing} in {list(df.columns)}")

    out = pd.DataFrame({
        "state": df[c_state] if c_state else None,
        "district": df[c_dist] if c_dist else None,
        "market_raw": df[c_market].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
        "commodity_raw": df[c_comm],
        "variety": df[c_var] if c_var else None,
        "grade": df[c_grade] if c_grade else None,
        "date": _dates(df[c_date]),
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


# ----------------------------------------------------------------------------- data.gov.in OGD API
def _relay_get(resource: str, filters: dict, limit: int, offset: int) -> dict:
    """Fetch through the app's Mumbai relay (data.gov.in refuses servers outside India, such as GitHub Actions)."""
    params = {"resource": "history" if resource == OGD_HISTORY else "current", "limit": limit, "offset": offset}
    commodity = filters.get("Commodity") or filters.get("commodity")
    if commodity:
        params["commodity"] = commodity
    if filters.get("Arrival_Date"):
        params["day"] = filters["Arrival_Date"]
    last_exc = None
    for _attempt in range(3):
        try:
            r = requests.get(os.environ["OGD_RELAY_URL"], params=params, timeout=60,
                             headers={"x-ingest-token": os.environ.get("OGD_RELAY_TOKEN", ""), "User-Agent": "MandiMitra-pipeline/1.0"})
            if r.status_code == 200:
                return r.json()
            last_exc = f"relay HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 403):
                break
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
    raise RuntimeError(f"relay failed: {last_exc}")


def _ogd_get(resource: str, key: str, filters: dict, limit: int, offset: int) -> dict:
    if os.environ.get("OGD_RELAY_URL"):
        return _relay_get(resource, filters, limit, offset)
    params = {"api-key": key, "format": "json", "limit": limit, "offset": offset}
    params.update({f"filters[{k}]": v for k, v in filters.items()})
    last_exc = None
    for _attempt in range(3):
        try:
            r = requests.get(OGD_BASE + resource, params=params, timeout=90, headers={"User-Agent": "MandiMitra-pipeline/1.0"})
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            continue
        if r.status_code >= 400 or str(data.get("status", "")).lower() == "error" or data.get("error"):
            raise RuntimeError(f"data.gov.in said: {data.get('message') or data.get('error') or r.status_code}")
        return data
    raise RuntimeError(f"data.gov.in unreachable: {last_exc}")


def _ogd_pages(resource: str, key: str, filters: dict, limit: int = 1000, max_pages: int = 400):
    """Page through a resource. Stops on an empty page, at `total`, or if the API repeats a page."""
    offset, first_prev = 0, None
    for _ in range(max_pages):
        data = _ogd_get(resource, key, filters, limit, offset)
        records = data.get("records") or []
        if not records or records[0] == first_prev:
            return
        first_prev = records[0]
        yield records, data.get("total")
        offset += len(records)
        total = data.get("total")
        if total is not None and offset >= int(total):
            return


def _ogd_pull(resource: str, key: str, variants: list[dict]) -> tuple[list[dict], dict | None, int | None]:
    """Try filter spellings in turn (field names differ between resources); keep the first that returns rows."""
    for filters in variants:
        rows, total = [], None
        for page, total in _ogd_pages(resource, key, filters):
            rows += page
        if rows:
            return rows, filters, total
    return [], None, None


def _to_raw(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=RAW_COLS)
    out = map_columns(pd.DataFrame(rows))
    out["source"] = "AGMARKNET"
    return out[RAW_COLS]


def _read_cache() -> pd.DataFrame:
    if not CACHE.exists():
        return pd.DataFrame(columns=RAW_COLS)
    df = pd.read_csv(CACHE, low_memory=False)
    for c in RAW_COLS:
        if c not in df.columns:
            df[c] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df[RAW_COLS]


def fetch_datagovin(catalog: dict, log: RunLog, history: bool) -> pd.DataFrame:
    """Official OGD API (needs DATA_GOV_IN_API_KEY); results are cached in data/raw/agmarknet/datagovin_cache.csv.

    - History (first run, --history, or a cache older than 30 days): every Andhra Pradesh record for each crop since
      HISTORY_START. All AP markets are kept, so the market cluster can change without pulling again.
    - Daily: each of the last REFRESH_DAYS days is re-read with an exact date filter (small, complete answers),
      plus today's file from the current-price resource.
    """
    key = os.environ.get("DATA_GOV_IN_API_KEY", "").strip()
    old = _read_cache()
    if not key and not os.environ.get("OGD_RELAY_URL"):
        return old
    state = catalog["state"]
    names = [n for c in catalog["crops"] for n in OGD_COMMODITIES.get(c["id"], [c["en"]])]
    core = {ckey(n) for n in names}
    extra_names = {ckey(n) for c in catalog.get("extra_crops", []) for n in c["agmarknet"]}
    today = date.today()
    need_history = history or old.empty or (pd.Timestamp(today) - old["date"].max()).days > 30
    frames: list[pd.DataFrame] = []
    extra_frames: list[pd.DataFrame] = []
    pulled_days: set[str] = set()

    def pull_day(day: str) -> int:
        """One request returns every AP commodity for that day: split into study crops and optional crops."""
        rows, _used, _total = _ogd_pull(OGD_HISTORY, key, [{"State": state, "Arrival_Date": day}])
        pulled_days.add(day)
        df = _to_raw(rows)
        if not df.empty:
            k = df["commodity_raw"].map(ckey)
            frames.append(df[k.isin(core)])
            extra_frames.append(df[k.isin(extra_names)])
        return len(rows)

    try:
        if need_history:
            for name in names:
                rows, used, total = _ogd_pull(OGD_HISTORY, key, [{"State": state, "Commodity": name},
                                                                  {"state": state, "commodity": name}])
                df = _to_raw(rows)
                uniq = len(pd.DataFrame(rows).drop_duplicates()) if rows else 0
                log.add("data_agent", "fetch_agmarknet",
                        f"data.gov.in history {name}: {len(rows)} records of {total} reported ({uniq} unique); "
                        f"{int((df['date'] >= pd.Timestamp(HISTORY_START)).sum())} since {HISTORY_START}")
                frames.append(df)
        else:
            got = 0
            for d in range(REFRESH_DAYS, -1, -1):
                got += pull_day((today - timedelta(days=d)).strftime("%d-%m-%Y"))
            log.add("data_agent", "fetch_agmarknet", f"data.gov.in history, last {REFRESH_DAYS} days re-read (all AP crops): {got} records")
        extra_old = _read_extra()
        if extra_names and (extra_old.empty or (pd.Timestamp(today) - extra_old["date"].max()).days > 20):
            got = 0
            for d in range(EXTRA_BACKFILL_DAYS, -1, -1):
                day = (today - timedelta(days=d)).strftime("%d-%m-%Y")
                if day not in pulled_days:
                    got += pull_day(day)
            log.add("data_agent", "fetch_agmarknet", f"optional crops: {EXTRA_BACKFILL_DAYS}-day backfill, {got} records")
        rows, _used, _total = _ogd_pull(OGD_CURRENT, key, [{"state.keyword": state}, {"state": state}])
        cur = _to_raw(rows)
        k = cur["commodity_raw"].map(ckey) if not cur.empty else pd.Series(dtype=str)
        if not cur.empty:
            extra_frames.append(cur[k.isin(extra_names)])
            cur = cur[k.isin(core)]
        frames.append(cur)
        log.add("data_agent", "fetch_agmarknet", f"data.gov.in current-day file: {len(rows)} AP records, {len(cur)} for our crops")
    except Exception as exc:
        log.add("data_agent", "fetch_agmarknet", f"data.gov.in fetch failed, using the cache: {exc}", level="warning")

    merge_extra(extra_frames, log)
    return merge_into_cache(old, frames, names, log)


def ckey(name) -> str:
    """Commodity names are compared without spaces/punctuation ('Red gram/Arhar/Tur(whole)' -> 'redgramarhartur...')."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _read_extra() -> pd.DataFrame:
    if not EXTRA_CACHE.exists():
        return pd.DataFrame(columns=RAW_COLS)
    df = pd.read_csv(EXTRA_CACHE, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def load_extra_cache() -> pd.DataFrame:
    return _read_extra()


def merge_extra(frames: list[pd.DataFrame], log: RunLog) -> None:
    """Keep the last EXTRA_KEEP_DAYS days of the optional crops (prices only, no forecasts)."""
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return
    allr = pd.concat([f for f in [_read_extra(), *frames] if not f.empty], ignore_index=True)
    allr["date"] = pd.to_datetime(allr["date"], errors="coerce")
    allr = allr[allr["date"] >= pd.Timestamp(date.today() - timedelta(days=EXTRA_KEEP_DAYS))]
    for c in ("market_raw", "variety", "grade", "district", "state", "commodity_raw"):
        allr[c] = allr[c].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    allr = allr.drop_duplicates(subset=["market_raw", "commodity_raw", "variety", "grade", "date"], keep="last")
    allr = allr.sort_values(["date", "commodity_raw", "market_raw"]).reset_index(drop=True)
    out = allr.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out[RAW_COLS].to_csv(EXTRA_CACHE, index=False)
    log.add("data_agent", "save_data", f"optional crops cache: {len(allr)} rows, {allr['commodity_raw'].nunique()} crops")


def merge_into_cache(old: pd.DataFrame, frames: list[pd.DataFrame], names: list[str], log: RunLog) -> pd.DataFrame:
    """Add freshly pulled rows to the cache (newest copy of a record wins) and save it."""
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return old
    allr = pd.concat([f for f in [old, *frames] if not f.empty], ignore_index=True)
    allr["date"] = pd.to_datetime(allr["date"], errors="coerce")
    allr = allr[allr["date"] >= pd.Timestamp(HISTORY_START)]
    allr = allr[allr["commodity_raw"].astype(str).str.strip().str.lower().isin([n.lower() for n in names])]
    for c in ("market_raw", "variety", "grade", "district", "state"):
        allr[c] = allr[c].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    allr = allr.drop_duplicates(subset=["market_raw", "commodity_raw", "variety", "grade", "date"], keep="last")
    allr = allr.sort_values(["date", "commodity_raw", "market_raw", "variety", "grade"]).reset_index(drop=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out = allr.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(CACHE, index=False)
    log.add("data_agent", "save_data", f"data.gov.in cache: {len(allr)} rows, {allr['date'].min().date()} to {allr['date'].max().date()}")
    return allr[RAW_COLS]


def load_real(catalog: dict, log: RunLog, history: bool = False) -> pd.DataFrame:
    parts = [load_csv_exports(log), fetch_datagovin(catalog, log, history)]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=RAW_COLS)
