"""Daily rainfall and temperature per market from Open-Meteo (free, no API key).

Archive data (ERA5) has a few days of lag, so the last two weeks come from the
forecast endpoint's `past_days`. Results are cached in data/raw/weather.csv and
fetched incrementally.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

from pipeline.common import RAW, RunLog

CACHE = RAW / "weather.csv"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
DAILY = "precipitation_sum,temperature_2m_max"
HEADERS = {"User-Agent": "MandiMitra-pipeline/1.0"}


def _frames(payload, markets: list[dict]) -> list[pd.DataFrame]:
    items = payload if isinstance(payload, list) else [payload]
    out = []
    for m, item in zip(markets, items):
        d = item.get("daily") or {}
        if not d.get("time"):
            continue
        out.append(pd.DataFrame({
            "date": pd.to_datetime(d["time"]),
            "market": m["id"],
            "rain_mm": d.get("precipitation_sum"),
            "tmax_c": d.get("temperature_2m_max"),
        }))
    return out


def _get(url: str, params: dict) -> list | dict:
    r = requests.get(url, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_weather(markets: list[dict], start: date, end: date, log: RunLog) -> pd.DataFrame:
    cached = pd.read_csv(CACHE, parse_dates=["date"]) if CACHE.exists() else pd.DataFrame()
    fetch_from = start
    if not cached.empty and set(m["id"] for m in markets) <= set(cached["market"].unique()):
        fetch_from = max(start, (cached["date"].max() - pd.Timedelta(days=10)).date())

    lat = ",".join(str(m["lat"]) for m in markets)
    lon = ",".join(str(m["lon"]) for m in markets)
    frames: list[pd.DataFrame] = []
    archive_end = min(end, date.today() - timedelta(days=6))
    try:
        if fetch_from <= archive_end:
            payload = _get(ARCHIVE, {"latitude": lat, "longitude": lon, "start_date": fetch_from.isoformat(),
                                     "end_date": archive_end.isoformat(), "daily": DAILY, "timezone": "Asia/Kolkata"})
            frames += _frames(payload, markets)
        payload = _get(FORECAST, {"latitude": lat, "longitude": lon, "daily": DAILY, "past_days": 14,
                                  "forecast_days": 1, "timezone": "Asia/Kolkata"})
        frames += _frames(payload, markets)
        log.add("data_agent", "fetch_weather", f"Open-Meteo rows fetched: {sum(len(f) for f in frames)} from {fetch_from}")
    except Exception as exc:  # network problems must not stop the daily run
        log.add("data_agent", "fetch_weather", f"Open-Meteo fetch failed, using cache: {exc}", level="warning")

    allw = pd.concat([cached, *frames], ignore_index=True) if frames else cached
    if allw.empty:
        return allw
    allw["date"] = pd.to_datetime(allw["date"])
    allw = allw.dropna(subset=["rain_mm", "tmax_c"], how="all")
    allw = allw.drop_duplicates(subset=["date", "market"], keep="last").sort_values(["market", "date"])
    allw = allw[allw["date"] <= pd.Timestamp(end)]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    allw.to_csv(CACHE, index=False, float_format="%.2f")
    return allw.reset_index(drop=True)
