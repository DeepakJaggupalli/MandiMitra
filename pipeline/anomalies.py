"""Unusual-movement detection: rolling statistics + Isolation Forest (detect_unusual tool).

An event needs a clear rule hit (big z-score move or arrival flood) confirmed by the
Isolation Forest, or an extreme rule hit on its own. Recent events become draft
warnings that an extension officer must approve before farmers see them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

RECENT_DAYS = 14


MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_TE = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జులై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"]


def _texts(kind: str, crop: dict, market: dict, iso: str, mag: float) -> tuple[str, str]:
    c_en, c_te, m_en, m_te = crop["en"], crop["te"], market["en"], market["te"]
    y, mo, d = (int(x) for x in iso.split("-"))
    date, date_te = f"{d} {MON_EN[mo - 1]}", f"{MON_TE[mo - 1]} {d}"
    if kind == "arrival_flood":
        x = f"{mag:.1f}"
        return (f"Arrival flood at {m_en}: {c_en} arrivals were {x} times the usual level on {date}. Prices may fall.",
                f"{m_te}లో {date_te}న {c_te} సరుకు రాక సాధారణం కంటే {x} రెట్లు ఎక్కువగా ఉంది. ధరలు తగ్గవచ్చు.")
    p = int(round(abs(mag)))
    if kind == "price_spike":
        return (f"{c_en} price at {m_en} jumped {p}% on {date}.", f"{m_te}లో {date_te}న {c_te} ధర {p}% పెరిగింది.")
    return (f"{c_en} price at {m_en} fell {p}% on {date}.", f"{m_te}లో {date_te}న {c_te} ధర {p}% తగ్గింది.")


def detect(panel: pd.DataFrame, catalog: dict, log) -> dict:
    crops = {c["id"]: c for c in catalog["crops"]}
    markets = {m["id"]: m for m in catalog["markets"]}
    frames = []
    for (crop, market), s in panel[panel["reported"]].groupby(["crop", "market"]):
        s = s[["crop", "market", "date", "modal", "arrivals_t", "spread"]].copy().sort_values("date")
        s["ret"] = np.log(s["modal"] / s["modal"].shift(1))
        s["sigma"] = s["ret"].rolling(30, min_periods=15).std().shift(1)
        s["z"] = s["ret"] / s["sigma"]
        s["arr_ratio"] = s["arrivals_t"] / s["arrivals_t"].rolling(28, min_periods=10).median().shift(1)
        frames.append(s)
    d = pd.concat(frames, ignore_index=True)
    d["if_flag"] = False
    for crop, idx in d.groupby("crop").groups.items():
        X = d.loc[idx, ["z", "arr_ratio", "spread"]].copy()
        X["z"] = X["z"].clip(-8, 8)
        X["arr_ratio"] = np.log(X["arr_ratio"].clip(0.05, 20))
        X = X.fillna(0.0)
        forest = IsolationForest(n_estimators=200, contamination=0.02, random_state=0).fit(X)
        d.loc[idx, "if_flag"] = forest.predict(X) == -1

    spike = ((d["z"] > 3) & (d["ret"] > np.log(1.12)) & d["if_flag"]) | (d["ret"] > np.log(1.40))
    crash = ((d["z"] < -3) & (d["ret"] < np.log(0.88)) & d["if_flag"]) | (d["ret"] < np.log(0.65))
    flood = ((d["arr_ratio"] > 2.0) & d["if_flag"]) | (d["arr_ratio"] > 3.0)
    events = []
    end_by_series = panel.groupby(["crop", "market"])["date"].max()
    for mask, kind in ((spike, "price_spike"), (crash, "price_crash"), (flood, "arrival_flood")):
        for _, r in d[mask].iterrows():
            mag = float(r["arr_ratio"]) if kind == "arrival_flood" else float(np.expm1(r["ret"]) * 100)
            date = str(r["date"].date())
            en, te = _texts(kind, crops[r["crop"]], markets[r["market"]], date, mag)
            recent = (end_by_series[(r["crop"], r["market"])] - r["date"]).days <= RECENT_DAYS
            events.append({"id": f"w-{r['crop']}-{r['market']}-{date}-{kind}", "crop": r["crop"], "market": r["market"],
                           "type": kind, "date": date, "magnitude": round(mag, 2), "en": en, "te": te, "recent": bool(recent)})
    events.sort(key=lambda e: e["date"], reverse=True)
    one_year = (panel["date"].max() - pd.Timedelta(days=365)).date().isoformat()
    events = [e for e in events if e["date"] >= one_year]
    recent = [e for e in events if e["recent"]]
    log.add("forecast_agent", "detect_unusual", f"{len(events)} unusual moves in the last year, {len(recent)} in the last {RECENT_DAYS} days")
    return {"events": events, "recent": recent}
