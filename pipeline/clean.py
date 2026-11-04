"""Data Agent: match names, convert units, remove duplicates, flag impossible values.

Flagged records are NOT used until an admin accepts them (data/reviews.json, or the
review table in the app database). Missing days are reported, never silently filled.
"""
from __future__ import annotations

import difflib
import json
import os
from datetime import date

import numpy as np
import pandas as pd

from pipeline.common import DATA, RunLog, norm

REVIEWS_PATH = DATA / "reviews.json"


def _lookup(catalog: dict):
    crop_names, market_names = {}, {}
    for c in catalog["crops"]:
        for n in [c["id"], c["en"], *c["agmarknet_names"], *c["aliases"]]:
            crop_names[norm(n)] = c["id"]
    for m in catalog["markets"]:
        for n in [m["id"], m["en"], *m["aliases"]]:
            market_names[norm(n)] = m["id"]
    return crop_names, market_names


def _match(value, table: dict, cache: dict) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    key = norm(value)
    if key in cache:
        return cache[key]
    hit = table.get(key)
    if hit is None:
        base = key.split("(")[0].strip()
        hit = table.get(base)
    if hit is None:
        close = difflib.get_close_matches(key, list(table), n=1, cutoff=0.86)
        hit = table[close[0]] if close else None
    cache[key] = hit
    return hit


def load_reviews() -> dict[str, str]:
    decisions: dict[str, str] = {}
    if REVIEWS_PATH.exists():
        decisions.update(json.loads(REVIEWS_PATH.read_text(encoding="utf-8")))
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            import psycopg  # optional, only in CI when the app DB is configured

            with psycopg.connect(url, connect_timeout=10) as conn:
                for rid, dec in conn.execute("SELECT record_id, decision FROM quality_reviews"):
                    decisions[rid] = dec
        except Exception as exc:  # the pipeline must still run
            print(f"review sync skipped: {exc}")
    return decisions


def clean(raw: pd.DataFrame, catalog: dict, as_of: date, log: RunLog) -> tuple[pd.DataFrame, dict]:
    crop_names, market_names = _lookup(catalog)
    allowed = {(c["id"], m) for c in catalog["crops"] for m in c["markets"]}
    rows_raw = len(raw)
    df = raw.copy()

    state_ok = df["state"].isna() | (df["state"].astype(str).map(norm) == norm(catalog["state"]))
    df = df[state_ok]
    cc, mc = {}, {}
    df["crop"] = df["commodity_raw"].map(lambda v: _match(v, crop_names, cc))
    df["market"] = df["market_raw"].map(lambda v: _match(v, market_names, mc))
    unmatched = df["crop"].isna() | df["market"].isna()
    df = df[~unmatched]
    df = df[[(c, m) in allowed for c, m in zip(df["crop"], df["market"])]]
    en_market = {m["id"]: norm(m["en"]) for m in catalog["markets"]}
    en_crop = {c["id"]: norm(c["en"]) for c in catalog["crops"]}
    name_fixes = int(((df["market_raw"].map(norm) != df["market"].map(en_market))
                      | (df["commodity_raw"].map(norm) != df["crop"].map(en_crop))).sum())
    log.add("data_agent", "match_names", f"{rows_raw} raw rows, {int(unmatched.sum())} outside cluster/unmatched, {name_fixes} names standardised")

    df = df.dropna(subset=["date", "modal"])
    df = df[df["modal"] > 0]
    for col in ("min", "max"):
        df[col] = df[col].fillna(df["modal"])
    kg = df["price_unit"].eq("kg")
    df.loc[kg, ["min", "max", "modal"]] *= 100

    before = len(df)
    df = df.drop_duplicates(subset=["crop", "market", "date", "variety", "modal"], keep="last")
    duplicates = before - len(df)

    # per-row unit errors: a price ~100x below the local median is a per-kg entry
    df = df.sort_values(["crop", "market", "date"])
    med = df.groupby(["crop", "market"])["modal"].transform(lambda s: s.rolling(21, min_periods=5, center=True).median())
    unit_err = (df["modal"] < 0.05 * med) & ((df["modal"] * 100 / med).between(0.4, 2.5))
    df.loc[unit_err, ["min", "max", "modal"]] *= 100
    unit_fixes = int(kg.sum() + unit_err.sum())
    log.add("data_agent", "convert_units", f"{unit_fixes} prices converted from Rs/kg to Rs/quintal; {duplicates} duplicates removed")

    # sanity rules -> flags
    med = df.groupby(["crop", "market"])["modal"].transform(lambda s: s.rolling(15, min_periods=5, center=True).median())
    flags = []
    rule_max_min = df["max"] < df["min"]
    rule_modal = ~rule_max_min & ((df["modal"] < df["min"] * 0.99) | (df["modal"] > df["max"] * 1.01))
    rel = np.log(df["modal"] / med).abs()
    rule_outlier = ~rule_max_min & ~rule_modal & (rel > np.log(2.2))
    for mask, rule, text in [(rule_max_min, "max_below_min", "Max price is below min price"),
                             (rule_modal, "modal_outside_range", "Modal price is outside the min-max range"),
                             (rule_outlier, "outlier", "Price is far from the usual level for this market")]:
        for _, r in df[mask].iterrows():
            rid = f"{r['crop']}|{r['market']}|{r['date'].date()}|{rule}"
            flags.append({"id": rid, "crop": r["crop"], "market": r["market"], "date": str(r["date"].date()),
                          "rule": rule, "detail": text, "min": float(r["min"]), "max": float(r["max"]),
                          "modal": float(r["modal"]), "_idx": r.name})
    decisions = load_reviews()
    exclude_idx = [f["_idx"] for f in flags if decisions.get(f["id"]) != "accept"]
    accepted_swap = [f["_idx"] for f in flags if decisions.get(f["id"]) == "accept" and f["rule"] == "max_below_min"]
    df.loc[accepted_swap, ["min", "max"]] = df.loc[accepted_swap, ["max", "min"]].values
    df = df.drop(index=exclude_idx)
    for f in flags:
        f.pop("_idx")
    log.add("data_agent", "check_quality", f"{len(flags)} records flagged, {len(exclude_idx)} held back until reviewed")

    # several varieties on one day -> one row per crop/market/day
    g = df.groupby(["crop", "market", "date"])
    clean_df = g.agg(min=("min", "min"), max=("max", "max"), modal=("modal", "median"),
                     arrivals_t=("arrivals_t", lambda s: s.sum(min_count=1)), varieties=("modal", "size")).reset_index()
    clean_df[["min", "max", "modal"]] = clean_df[["min", "max", "modal"]].round(0)

    markets = {m["id"]: m for m in catalog["markets"]}
    stale_days = catalog["defaults"]["stale_after_days"]
    series = []
    for (crop, market), s in clean_df.groupby(["crop", "market"]):
        days = pd.date_range(s["date"].min(), s["date"].max(), freq="D")
        closed = markets[market]["closed_weekday"]
        expected = int((days.day_of_week != closed).sum()) if closed is not None else len(days)
        missing = max(expected - len(s), 0)
        last = s["date"].max().date()
        series.append({"crop": crop, "market": market, "first_date": str(s["date"].min().date()), "last_date": str(last),
                       "days_reported": int(len(s)), "missing_days": missing,
                       "missing_pct": round(100 * missing / max(expected, 1), 1),
                       "flagged": sum(1 for f in flags if f["crop"] == crop and f["market"] == market),
                       "stale": (as_of - last).days > stale_days})
    expected_pairs = sorted(allowed)
    present = {(s["crop"], s["market"]) for s in series}
    checks = [
        {"name": "All crop-market pairs have data", "passed": present >= set(expected_pairs),
         "detail": f"{len(present)} of {len(expected_pairs)} pairs" + ("" if present >= set(expected_pairs) else
                   " (missing: " + ", ".join(f"{c}/{m}" for c, m in expected_pairs if (c, m) not in present) + ")")},
        {"name": "Data is fresh", "passed": all(not s["stale"] for s in series),
         "detail": f"{sum(s['stale'] for s in series)} series older than {stale_days} days"},
        {"name": "Missing days below 15%", "passed": all(s["missing_pct"] < 15 for s in series),
         "detail": f"worst {max((s['missing_pct'] for s in series), default=0)}%"},
        {"name": "At least 3 years of history", "passed": all((pd.Timestamp(s['last_date']) - pd.Timestamp(s['first_date'])).days >= 3 * 365 - 10 for s in series),
         "detail": f"shortest {min(((pd.Timestamp(s['last_date']) - pd.Timestamp(s['first_date'])).days for s in series), default=0)} days"},
        {"name": "Flagged records reviewed", "passed": len(exclude_idx) == 0,
         "detail": f"{len(exclude_idx)} waiting for admin review"},
    ]
    report = {"rows_raw": rows_raw, "rows_clean": int(len(clean_df)), "duplicates_removed": int(duplicates),
              "name_fixes": name_fixes, "unit_fixes": unit_fixes, "unmatched_rows": int(unmatched.sum()),
              "checks": checks, "series": series, "flagged": flags}
    log.add("data_agent", "save_data", f"{len(clean_df)} clean daily rows across {len(series)} crop-market series")
    return clean_df, report
