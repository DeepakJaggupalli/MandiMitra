"""Optional crops a farmer can add in the app: latest official price per market, prices only (no forecast).

Forecasts stay limited to the study crops (tomato, onion, banana), which are the only ones backtested.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from pipeline.sources.agmarknet import ckey

MAX_AGE_DAYS = 30      # a market is listed if it reported this crop in the last 30 days
RECENT_DAYS = 14       # "N markets" counts markets that reported in the last 14 days
HISTORY_DAYS = 30


def _market_label(raw: str) -> str:
    """'Divi (HQ-Avanigadda APMC)' -> 'Divi (HQ-Avanigadda)'; 'RAYADURG' -> 'Rayadurg'."""
    name = re.sub(r"\s*\bAPMC\b\s*", " ", str(raw))
    name = re.sub(r"\(\s*\)", "", name)
    name = re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", name))
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name.title() if name.isupper() else name


def build_extra(raw: pd.DataFrame, catalog: dict, as_of: date) -> dict:
    out = {"as_of": str(as_of), "crops": []}
    place_te = {}
    for p in catalog.get("places", []):
        for n in [p["en"].split(" (")[0], *p.get("aliases", [])]:
            if p.get("te"):
                place_te[ckey(n)] = p["te"]
    df = raw.copy() if raw is not None else pd.DataFrame()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "modal"])
        df["ck"] = df["commodity_raw"].map(ckey)
        for col in ("min", "max", "modal"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # plausibility: positive per-quintal prices only; a missing/zero min or max takes the modal
        df = df[(df["modal"] > 0) & (df["modal"] < 200000)]
        for col in ("min", "max"):
            df.loc[~(df[col] > 0), col] = df["modal"]
        df = df[df["min"] <= df["max"]]
        df["mk"] = df["market_raw"].map(_market_label)
    for crop in catalog.get("extra_crops", []):
        names = {ckey(n) for n in crop["agmarknet"]}
        g = df[df["ck"].isin(names)] if not df.empty else df
        markets = []
        if not g.empty:
            for mk, gm in g.groupby("mk"):
                last_day = gm["date"].max()
                if (as_of - last_day.date()).days > MAX_AGE_DAYS:
                    continue
                today = gm[gm["date"] == last_day]
                daily = (gm[gm["date"] > last_day - pd.Timedelta(days=HISTORY_DAYS)]
                         .groupby("date").agg(min=("min", "min"), max=("max", "max"), modal=("modal", "median")).reset_index())
                base = ckey(re.sub(r"\(.*\)", "", mk))
                markets.append({
                    "market": mk, "te": place_te.get(base), "district": str(today["district"].iloc[0]),
                    "date": str(last_day.date()), "min": int(today["min"].min()), "max": int(today["max"].max()),
                    "modal": int(round(today["modal"].median())),
                    "varieties": sorted({v for v in today["variety"].astype(str) if v and v != "nan"}),
                    "history": [[str(r.date.date()), int(r.min), int(r.max), int(round(r.modal))] for r in daily.itertuples()],
                })
        markets.sort(key=lambda m: (m["date"], m["modal"]), reverse=True)
        recent = [m for m in markets if (as_of - date.fromisoformat(m["date"])).days <= RECENT_DAYS]
        out["crops"].append({"id": crop["id"], "en": crop["en"], "te": crop["te"], "group": crop["group"],
                             "n_markets": len(recent), "last_date": markets[0]["date"] if markets else None,
                             "markets": markets})
    return out
