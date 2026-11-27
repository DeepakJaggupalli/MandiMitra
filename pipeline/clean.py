"""Data Agent: match names, convert units, remove duplicates, flag impossible values.

Flagged records are NOT used until an admin accepts them (data/reviews.json, or the
review table in the app database). Missing days are reported, never silently filled.
"""
from __future__ import annotations

import difflib
import json
import os
import re
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
        for n in [m["id"], m["en"], *m.get("data_names", m.get("aliases", []))]:
            market_names[norm(n)] = m["id"]
    return crop_names, market_names


def _variants(key: str) -> list[str]:
    """'madanapalli apmc' -> ['madanapalli apmc', 'madanapalli']; 'ravulapalem (kothapeta apmc)' -> [..., 'ravulapalem']."""
    out = [key]
    no_apmc = re.sub(r"\b(apmc|amc)\b", " ", key)
    no_apmc = re.sub(r"\s+", " ", no_apmc).strip()
    out.append(no_apmc)
    out.append(no_apmc.split("(")[0].strip())
    out.append(key.split("(")[0].strip())
    return [v for v in dict.fromkeys(out) if v]


def _match(value, table: dict, cache: dict) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    key = norm(value)
    if key in cache:
        return cache[key]
    hit = None
    for v in _variants(key):
        hit = table.get(v)
        if hit:
            break
    if hit is None:
        vs = _variants(key)
        close = difflib.get_close_matches(vs[1] if len(vs) > 1 else vs[0], list(table), n=1, cutoff=0.88)
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
    log.add("data_agent", "match_names", f"{rows_raw} raw rows, {int(unmatched.sum())} from markets/crops outside the PoC cluster, {name_fixes} names standardised")

    df = df.dropna(subset=["date", "modal"])
    df = df[df["modal"] > 0]
    zero_fixes = int(((df["min"] <= 0) | (df["max"] <= 0)).sum())
    for col in ("min", "max"):
        df.loc[df[col] <= 0, col] = np.nan
        df[col] = df[col].fillna(df["modal"])
    kg = df["price_unit"].eq("kg")
    df.loc[kg, ["min", "max", "modal"]] *= 100

    before = len(df)
    if "grade" not in df.columns:
        df["grade"] = None
    for c in ("variety", "grade"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = df.drop_duplicates(subset=["crop", "market", "date", "variety", "grade"], keep="last")
    duplicates = before - len(df)

    # per-row unit errors: a price ~100x below the local median is a per-kg entry
    df = df.sort_values(["crop", "market", "date"])
    med = df.groupby(["crop", "market"])["modal"].transform(lambda s: s.rolling(21, min_periods=5, center=True).median())
    unit_err = (df["modal"] < 0.05 * med) & ((df["modal"] * 100 / med).between(0.4, 2.5))
    df.loc[unit_err, ["min", "max", "modal"]] *= 100
    unit_fixes = int(kg.sum() + unit_err.sum())
    log.add("data_agent", "convert_units", f"{unit_fixes} prices converted from Rs/kg to Rs/quintal; {duplicates} duplicates removed; "
                                           f"{zero_fixes} zero min/max values replaced by the modal")

    # sanity rules -> flags
    med = df.groupby(["crop", "market", "variety", "grade"])["modal"].transform(
        lambda s: s.rolling(15, min_periods=5, center=True).median())
    flags = []
    rule_max_min = df["max"] < df["min"]
    rule_modal = ~rule_max_min & ((df["modal"] < df["min"] * 0.99) | (df["modal"] > df["max"] * 1.01))
    rel = np.log(df["modal"] / med).abs()
    rule_outlier = ~rule_max_min & ~rule_modal & (rel > np.log(2.2))
    for mask, rule, text in [(rule_max_min, "max_below_min", "Max price is below min price"),
                             (rule_modal, "modal_outside_range", "Modal price is outside the min-max range"),
                             (rule_outlier, "outlier", "Price is far from the usual level for this market")]:
        for _, r in df[mask].iterrows():
            rid = f"{r['crop']}|{r['market']}|{r['date'].date()}|{r['variety']}|{rule}"
            flags.append({"id": rid, "crop": r["crop"], "market": r["market"], "date": str(r["date"].date()),
                          "variety": r["variety"], "grade": r["grade"],
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

    # One consistent price line per crop-market. Markets report in two ways:
    #  - several varieties/grades a day (e.g. Madanapalle: Local plus a cheaper "Other"): follow the variety that is
    #    reported on >= 75% of days (then its dominant grade the same way), so the line is not dragged by a cheaper lot;
    #  - one record a day whose variety label changes over time (e.g. Kalikiri: "Local" in 2024, "Hybrid" in 2025):
    #    that record is the market's daily tomato price, so it is followed whatever the label.
    # Today's price for every variety reported is kept separately for the app.
    parts, series_info, latest_varieties = [], {}, {}
    for (crop, market), g in df.groupby(["crop", "market"]):
        recent = g[g["date"] >= g["date"].max() - pd.Timedelta(days=3 * 365)]
        days = max(recent["date"].nunique(), 1)
        per_day = recent.groupby("date").size()
        multi = (per_day > 1).mean() if len(per_day) else 0.0
        v_counts = recent.groupby("variety")["date"].nunique().sort_values(ascending=False)
        top_v, v_share = (v_counts.index[0], v_counts.iloc[0] / days) if len(v_counts) else ("", 0.0)
        use, variety, grade, method = g, "", "", "daily"
        everyday = list(v_counts[v_counts / days >= 0.75].index)
        if len(v_counts) <= 1:
            use, variety, method = g, top_v, "single"
        elif len(everyday) >= 2:
            use, method = g[g["variety"].isin(everyday)], "median"   # several main varieties: their daily median
        elif v_share >= 0.75:
            use, variety, method = g[g["variety"] == top_v], top_v, "dominant"
        elif multi < 0.05:
            method = "daily"   # one record a day, label changes: keep all
        else:
            method = "median"  # several varieties a day and none dominant: daily median
        if method in ("single", "dominant"):
            rv = use[use["date"] >= use["date"].max() - pd.Timedelta(days=3 * 365)]
            g_counts = rv.groupby("grade")["date"].nunique().sort_values(ascending=False)
            if len(g_counts) > 1 and g_counts.iloc[0] / max(rv["date"].nunique(), 1) >= 0.75 and (rv.groupby("date").size() > 1).any():
                grade = g_counts.index[0]
                use = use[use["grade"] == grade]
            elif len(g_counts) == 1:
                grade = g_counts.index[0]
        parts.append(use)
        series_info[(crop, market)] = {"variety": variety, "grade": grade, "method": method,
                                       "variety_share": round(float(v_share), 2), "varieties_seen": int(len(v_counts)),
                                       "main_varieties": everyday if method == "median" else []}
        last_day = g["date"].max()
        latest_varieties[(crop, market)] = [
            {"variety": r["variety"], "grade": r["grade"], "min": int(r["min"]), "max": int(r["max"]), "modal": int(r["modal"])}
            for _, r in g[g["date"] == last_day].sort_values("modal", ascending=False).iterrows()]
    df = pd.concat(parts) if parts else df.iloc[0:0]
    g = df.groupby(["crop", "market", "date"])
    clean_df = g.agg(min=("min", "min"), max=("max", "max"), modal=("modal", "median"),
                     arrivals_t=("arrivals_t", lambda s: s.sum(min_count=1)), varieties=("modal", "size")).reset_index()
    clean_df[["min", "max", "modal"]] = clean_df[["min", "max", "modal"]].round(0)

    # A feed that repeats the same modal price 15+ reports in a row has stopped updating (e.g. Kuppam: Rs 1,212 for 67
    # reports while nearby markets moved between Rs 1,000 and 4,200). The repeats are left out of the series; if the
    # repeat is still going on, the market is shown as "not updated since <date>" with no forecast.
    STUCK_RUN = 15
    clean_df = clean_df.sort_values(["crop", "market", "date"]).reset_index(drop=True)
    stuck_idx, frozen = [], {}
    for (crop, market), sdf in clean_df.groupby(["crop", "market"]):
        vals, idxs = sdf["modal"].to_numpy(), sdf.index.to_numpy()
        start = 0
        for i in range(1, len(vals) + 1):
            if i == len(vals) or vals[i] != vals[start]:
                if i - start >= STUCK_RUN:
                    stuck_idx.extend(idxs[start + 1:i])
                    if i == len(vals):
                        frozen[(crop, market)] = {"frozen_since": str(sdf["date"].iloc[start].date()),
                                                  "last_report": str(sdf["date"].iloc[-1].date()), "repeats": int(i - start)}
                start = i
    clean_df = clean_df.drop(index=stuck_idx).reset_index(drop=True)
    for key, info in frozen.items():
        series_info.setdefault(key, {}).update(info)
        latest_varieties[key] = []
    log.add("data_agent", "check_quality", f"{len(stuck_idx)} repeated reports left out (price not updating at source); "
                                           f"frozen now: {', '.join(f'{c}/{m} since {v['frozen_since']}' for (c, m), v in frozen.items()) or 'none'}")

    stale_days = catalog["defaults"]["stale_after_days"]
    series = []
    for (crop, market), s in clean_df.groupby(["crop", "market"]):
        days = pd.date_range(s["date"].min(), s["date"].max(), freq="D")
        wd = s["date"].dt.day_of_week.value_counts().reindex(range(7), fill_value=0)
        closed = [d for d in range(7) if wd[d] < 0.2 * wd.mean()]  # weekly closing days, read from the data
        expected = int((~days.day_of_week.isin(closed)).sum())
        missing = max(expected - len(s), 0)
        last = s["date"].max().date()
        series.append({"crop": crop, "market": market, "first_date": str(s["date"].min().date()), "last_date": str(last),
                       "days_reported": int(len(s)), "missing_days": missing,
                       "missing_pct": round(100 * missing / max(expected, 1), 1),
                       "flagged": sum(1 for f in flags if f["crop"] == crop and f["market"] == market),
                       "stale": (as_of - last).days > stale_days, "closed_weekdays": closed,
                       **series_info.get((crop, market), {})})
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
        {"name": "No market price frozen at the source", "passed": not frozen,
         "detail": ", ".join(f"{c}/{m}: same price for {v['repeats']} reports since {v['frozen_since']}" for (c, m), v in frozen.items()) or "none"},
    ]
    report = {"rows_raw": rows_raw, "rows_clean": int(len(clean_df)), "duplicates_removed": int(duplicates),
              "name_fixes": name_fixes, "unit_fixes": unit_fixes, "unmatched_rows": int(unmatched.sum()),
              "zero_fixes": zero_fixes, "stuck_rows_removed": len(stuck_idx),
              "checks": checks, "series": series, "flagged": flags,
              "latest_varieties": {f"{c}|{m}": v for (c, m), v in latest_varieties.items()}}
    log.add("data_agent", "save_data", f"{len(clean_df)} clean daily rows across {len(series)} crop-market series")
    return clean_df, report
