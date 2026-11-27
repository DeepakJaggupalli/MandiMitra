"""Best market finder: rank markets by money in hand after transport, commission and handling."""
from __future__ import annotations

from backend.app.store import Store, haversine_km


def compare_markets(store: Store, crop: str, quantity_qtl: float, lat: float, lon: float,
                    rate: float | None = None, commission_pct: float | None = None, handling: float | None = None,
                    max_km: float | None = None) -> dict:
    """Markets farther than max_km by road are left out (a farmer will not haul a perishable crop across the state).
    If none is that close, the 3 nearest are shown and `far_only` says so."""
    d = store.defaults
    rate = d["transport_rate_per_qtl_km"] if rate is None else max(0.0, float(rate))
    commission_pct = d["commission_pct"] if commission_pct is None else min(max(0.0, float(commission_pct)), 30.0)
    handling = d["handling_per_qtl"] if handling is None else max(0.0, float(handling))
    qty = max(0.1, float(quantity_qtl))
    max_km = float(d.get("max_compare_km", 200)) if max_km is None else max(10.0, float(max_km))
    rows = []
    for m in store.crops[crop]["markets"]:
        if not store.has(crop, m):
            continue
        last = store.latest(crop, m)
        mk = store.markets[m]
        dist = haversine_km(lat, lon, mk["lat"], mk["lon"]) * d["road_factor"]
        transport = round(rate * dist)
        commission = round(last["modal"] * commission_pct / 100)
        net = last["modal"] - transport - commission - round(handling)
        flags = []
        an = store.recent_anomaly(crop, m)
        if an and an["type"] == "arrival_flood":
            flags.append("arrival_flood")
        if store.stale(last["date"]):
            flags.append("stale")
        fc = store.forecast(crop, m) or {}
        ser = store.series(crop, m) or {}
        rows.append({"market": m, "date": last["date"], "modal": last["modal"], "distance_km": round(dist, 1),
                     "variety": ser.get("variety", ""), "price_method": ser.get("price_method", ""),
                     "_stale": store.stale(last["date"]),
                     "transport": transport, "commission": commission, "handling": round(handling),
                     "net_per_qtl": net, "net_total": round(net * qty), "badges": [], "flags": flags,
                     "forecast": ({k: fc["summary"][k] for k in ("point_mean", "lo", "hi")} | {"confidence": "low" if flags else fc["confidence"]})
                     if fc.get("available") else None})
    fresh = [r for r in rows if not r["_stale"]]          # an old or frozen price is not a basis for a trip
    excluded_stale = len(rows) - len(fresh)
    for r in rows:
        r.pop("_stale", None)
    rows = fresh
    near = [r for r in rows if r["distance_km"] <= max_km]
    far_only = not near and bool(rows)
    excluded = len(rows) - len(near)
    if far_only:
        near = sorted(rows, key=lambda r: r["distance_km"])[:3]
        excluded = len(rows) - len(near)
    rows = near
    rows.sort(key=lambda r: -r["net_per_qtl"])
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    best_vs_nearest = None
    varieties_differ = False
    if rows:
        rows[0]["badges"].append("best")
        max(rows, key=lambda r: r["modal"])["badges"].append("highest_price")
        nearest = min(rows, key=lambda r: r["distance_km"])
        nearest["badges"].append("nearest")
        extra = rows[0]["net_per_qtl"] - nearest["net_per_qtl"]
        comparable = store.crops[crop].get("compare_across_varieties", True) or (
            rows[0]["variety"] and rows[0]["variety"] == nearest["variety"] and rows[0]["price_method"] != "median")
        if comparable or rows[0]["market"] == nearest["market"]:
            best_vs_nearest = {"best": rows[0]["market"], "nearest": nearest["market"], "extra_per_qtl": extra, "extra_total": round(extra * qty)}
        else:
            varieties_differ = True
    return {"crop": crop, "quantity_qtl": qty, "origin": {"lat": lat, "lon": lon},
            "assumptions": {"transport_rate_per_qtl_km": rate, "commission_pct": commission_pct, "handling_per_qtl": handling,
                            "road_factor": d["road_factor"], "max_km": max_km},
            "excluded_far": excluded, "far_only": far_only, "excluded_stale": excluded_stale, "varieties_differ": varieties_differ,
            "rows": rows, "best_vs_nearest": best_vs_nearest, "source": store.source, "data_as_of": store.meta["data_as_of"]}
