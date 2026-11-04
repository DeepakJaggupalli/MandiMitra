"""Read-only access to the pipeline output (data/processed/*.json). Loaded once per process."""
from __future__ import annotations

import json
import math
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from functools import lru_cache

from backend.app.settings import DATA_DIR, PROCESSED_DIR


def _load(name: str):
    with open(PROCESSED_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def pct(a: float, b: float) -> float | None:
    if a is None or b is None or not b:
        return None
    return round((a / b - 1) * 100, 1)


def trend_label(change: float | None) -> str:
    if change is None:
        return "steady"
    return "rising" if change > 3 else "falling" if change < -3 else "steady"


class Store:
    def __init__(self) -> None:
        self.meta = _load("meta.json")
        self.prices = _load("prices.json")
        self.forecasts = _load("forecasts.json")
        self.accuracy = _load("accuracy.json")
        self.quality = _load("quality.json")
        self.anomalies = _load("anomalies.json")
        with open(DATA_DIR / "catalog.json", encoding="utf-8") as f:
            self.catalog = json.load(f)
        self.crops = {c["id"]: c for c in self.catalog["crops"]}
        self.markets = {m["id"]: m for m in self.catalog["markets"]}
        self.places = self.catalog["places"]
        self.defaults = self.catalog["defaults"]
        self.data_as_of = date.fromisoformat(self.meta["data_as_of"])
        self.source = self.meta["source"]

    # ------------------------------------------------------------------ helpers
    def has(self, crop: str, market: str) -> bool:
        return f"{crop}|{market}" in self.prices

    def series(self, crop: str, market: str) -> dict | None:
        return self.prices.get(f"{crop}|{market}")

    def forecast(self, crop: str, market: str) -> dict | None:
        return self.forecasts.get(f"{crop}|{market}")

    def _value_on_or_before(self, s: dict, day: date, key: str = "modal"):
        i = bisect_right(s["dates"], day.isoformat()) - 1
        return s[key][i] if i >= 0 else None

    def latest(self, crop: str, market: str) -> dict | None:
        s = self.series(crop, market)
        if not s:
            return None
        i = len(s["dates"]) - 1
        return {"date": s["dates"][i], "min": s["min"][i], "max": s["max"][i], "modal": s["modal"][i], "arrivals_t": s["arr"][i]}

    def trend(self, crop: str, market: str) -> dict:
        s = self.series(crop, market)
        last = self.latest(crop, market)
        d = date.fromisoformat(last["date"])
        c7 = pct(last["modal"], self._value_on_or_before(s, d - timedelta(days=7)))
        c30 = pct(last["modal"], self._value_on_or_before(s, d - timedelta(days=30)))
        lo = bisect_right(s["dates"], (d - timedelta(days=7)).isoformat())
        lo2 = bisect_right(s["dates"], (d - timedelta(days=14)).isoformat())
        a_now = [a for a in s["arr"][lo:] if a is not None]
        a_prev = [a for a in s["arr"][lo2:lo] if a is not None]
        arr_chg = pct(sum(a_now) / len(a_now), sum(a_prev) / len(a_prev)) if a_now and a_prev else None
        last6 = s["modal"][-6:]
        moves = [b - a for a, b in zip(last6, last6[1:])]
        return {"label": trend_label(c7), "change_7d_pct": c7, "change_30d_pct": c30, "arrivals_change_7d_pct": arr_chg,
                "down_days_last5": sum(1 for m in moves if m < 0), "up_days_last5": sum(1 for m in moves if m > 0)}

    def stale(self, day: str) -> bool:
        return (self.data_as_of - date.fromisoformat(day)).days > self.defaults["stale_after_days"]

    def history(self, crop: str, market: str, days: int) -> list[dict]:
        s = self.series(crop, market)
        start = (self.data_as_of - timedelta(days=days - 1)).isoformat()
        i = bisect_left(s["dates"], start)
        return [{"date": s["dates"][k], "min": s["min"][k], "max": s["max"][k], "modal": s["modal"][k], "arrivals_t": s["arr"][k]}
                for k in range(i, len(s["dates"]))]

    def last_year(self, crop: str, market: str, days: int) -> list[dict]:
        s = self.series(crop, market)
        end = self.data_as_of - timedelta(days=365)
        start = end - timedelta(days=days - 1)
        out = []
        for k, ds in enumerate(s["dates"]):
            if start.isoformat() <= ds <= end.isoformat():
                out.append({"date": (date.fromisoformat(ds) + timedelta(days=365)).isoformat(), "modal": s["modal"][k]})
        return out

    def latest_rows(self, crop: str) -> list[dict]:
        rows = []
        for m in self.crops[crop]["markets"]:
            if not self.has(crop, m):
                continue
            last = self.latest(crop, m)
            t = self.trend(crop, m)
            rows.append({"market": m, **last, "change_7d_pct": t["change_7d_pct"], "trend": t["label"], "stale": self.stale(last["date"])})
        return rows

    def recent_anomaly(self, crop: str, market: str) -> dict | None:
        return next((e for e in self.anomalies.get("recent", []) if e["crop"] == crop and e["market"] == market), None)


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
