"""Best market finder: rank markets by money in hand after transport, commission and handling."""
from __future__ import annotations

from backend.app.store import Store, haversine_km


def compare_markets(store: Store, crop: str, quantity_qtl: float, lat: float, lon: float,
                    rate: float | None = None, commission_pct: float | None = None, handling: float | None = None) -> dict:
    d = store.defaults
    rate = d["transport_rate_per_qtl_km"] if rate is None else max(0.0, float(rate))
    commission_pct = d["commission_pct"] if commission_pct is None else min(max(0.0, float(commission_pct)), 30.0)
    handling = d["handling_per_qtl"] if handling is None else max(0.0, float(handling))
    qty = max(0.1, float(quantity_qtl))
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
        rows.append({"market": m, "date": last["date"], "modal": last["modal"], "distance_km": round(dist, 1),
                     "transport": transport, "commission": commission, "handling": round(handling),
                     "net_per_qtl": net, "net_total": round(net * qty), "badges": [], "flags": flags,
                     "forecast": ({k: fc["summary"][k] for k in ("point_mean", "lo", "hi")} | {"confidence": "low" if flags else fc["confidence"]})
                     if fc.get("available") else None})
    rows.sort(key=lambda r: -r["net_per_qtl"])
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    best_vs_nearest = None
    if rows:
        rows[0]["badges"].append("best")
        max(rows, key=lambda r: r["modal"])["badges"].append("highest_price")
        nearest = min(rows, key=lambda r: r["distance_km"])
        nearest["badges"].append("nearest")
        extra = rows[0]["net_per_qtl"] - nearest["net_per_qtl"]
        best_vs_nearest = {"best": rows[0]["market"], "nearest": nearest["market"], "extra_per_qtl": extra, "extra_total": round(extra * qty)}
    return {"crop": crop, "quantity_qtl": qty, "origin": {"lat": lat, "lon": lon},
            "assumptions": {"transport_rate_per_qtl_km": rate, "commission_pct": commission_pct, "handling_per_qtl": handling,
                            "road_factor": d["road_factor"]},
            "rows": rows, "best_vs_nearest": best_vs_nearest, "source": store.source, "data_as_of": store.meta["data_as_of"]}
