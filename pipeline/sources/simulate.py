"""Simulated AGMARKNET-format records for demos and tests.

Used ONLY when no real price data is available. Everything produced from it is
labelled SIMULATED in the API and the app. The generator is deterministic: the
same calendar day always gets the same value, so daily runs extend the series
without rewriting history.

Model of the market (so the ML has realistic signals to learn):
- regional supply follows the crop calendar, AR(1) noise, and drops after heavy rain;
- price reacts to supply with a short lag (elasticity per crop), plus persistent
  demand noise, occasional shocks (festivals, rain damage) and slow inflation;
- each market has its own price level, arrival share, noise and weekly closure;
- the raw file contains the usual reporting problems (name variants, duplicates,
  swapped min/max, price entered per kg, missing days) so the Data Agent's
  cleaning rules are exercised exactly as on real data.
"""
from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd

SIM_START = date(2023, 1, 1)
SIM_END_FIXED = date(2027, 12, 31)

CROP = {
    "tomato": dict(base=1650, elasticity=1.1, sigma=0.030, supply_amp=0.55, harvest_doy=30, jump_rate=5,
                   jump_size=0.28, spread=(0.18, 0.40), base_arr=900.0),
    "onion": dict(base=1900, elasticity=0.85, sigma=0.020, supply_amp=0.45, harvest_doy=290, jump_rate=3,
                  jump_size=0.20, spread=(0.10, 0.25), base_arr=600.0),
    "banana": dict(base=1550, elasticity=0.55, sigma=0.011, supply_amp=0.30, harvest_doy=75, jump_rate=2,
                   jump_size=0.12, spread=(0.08, 0.18), base_arr=250.0),
}
# (log price offset, arrival share, transmission lag in days)
MARKET = {
    "tomato": {"madanapalle": (-0.03, 1.00, 0), "pattikonda": (-0.05, 0.45, 0), "kurnool": (0.02, 0.20, 1),
               "anantapur": (0.00, 0.18, 1), "kadapa": (0.03, 0.12, 1), "tirupati": (0.07, 0.10, 1),
               "vijayawada": (0.10, 0.25, 2)},
    "onion": {"kurnool": (-0.04, 1.00, 0), "anantapur": (0.00, 0.15, 1), "kadapa": (0.02, 0.12, 1),
              "madanapalle": (0.04, 0.08, 1), "tirupati": (0.06, 0.10, 1), "vijayawada": (0.08, 0.30, 1)},
    "banana": {"pulivendula": (-0.05, 1.00, 0), "kadapa": (-0.01, 0.50, 0), "anantapur": (0.01, 0.40, 1),
               "kurnool": (0.03, 0.20, 1), "tirupati": (0.06, 0.30, 1), "vijayawada": (0.05, 0.60, 2)},
}
HOLIDAYS = {(1, 26), (8, 15), (10, 2), (1, 14), (1, 15)}


def _rng(*keys: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(keys).encode()))


def _ar1(rng: np.random.Generator, n: int, phi: float, sigma: float) -> np.ndarray:
    eps = rng.normal(0.0, sigma, n)
    x = np.empty(n)
    x[0] = eps[0] / np.sqrt(1 - phi**2)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return x


def _ema(x: np.ndarray, alpha: float) -> np.ndarray:
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _sim_rain(days: pd.DatetimeIndex, key: str) -> np.ndarray:
    rng = _rng("rain", key)
    month = days.month.values
    monsoon = (month >= 6) & (month <= 11)
    p = np.where(monsoon, 0.35, 0.05)
    wet = rng.random(len(days)) < p
    return np.where(wet, rng.gamma(0.8, 14.0, len(days)), 0.0)


def simulate(catalog: dict, end: date, weather: pd.DataFrame | None = None) -> pd.DataFrame:
    days = pd.date_range(SIM_START, SIM_END_FIXED, freq="D")
    n = len(days)
    doy = days.day_of_year.values
    markets = {m["id"]: m for m in catalog["markets"]}

    rain_by_market: dict[str, np.ndarray] = {}
    for mid in markets:
        sim = _sim_rain(days, mid)
        if weather is not None and not weather.empty:
            w = weather[weather["market"] == mid].set_index("date")["rain_mm"]
            real = w.reindex(days).values
            sim = np.where(np.isnan(real), sim, real)
        rain_by_market[mid] = sim

    rows = []
    for crop in catalog["crops"]:
        cid = crop["id"]
        p = CROP[cid]
        mk = [m for m in crop["markets"] if m in MARKET[cid]]
        region_rain = np.mean([rain_by_market[m] for m in mk], axis=0)
        rain5 = pd.Series(region_rain).rolling(5, min_periods=1).sum().values

        seasonal = p["supply_amp"] * np.cos(2 * np.pi * (doy - p["harvest_doy"]) / 365.25)
        u = _ar1(_rng(cid, "supply"), n, 0.92, 0.10)
        rain_eff = -np.minimum(0.010 * rain5, 0.45)
        log_supply = seasonal + u + rain_eff
        smooth = np.roll(_ema(log_supply, 0.35), 1)
        smooth[0] = log_supply[0]

        v = _ar1(_rng(cid, "demand"), n, 0.985, p["sigma"])
        jr = _rng(cid, "jumps")
        events = jr.random(n) < p["jump_rate"] / 365.0
        sizes = np.where(events, jr.normal(p["jump_size"], p["jump_size"] / 3, n) * jr.choice([-1, 1], n, p=[0.4, 0.6]), 0.0)
        jumps = np.zeros(n)
        for i in range(n):
            jumps[i] = (0.93 * jumps[i - 1] if i else 0.0) + sizes[i]
        inflation = np.arange(n) * np.log(1.05) / 365.25
        log_region = np.log(p["base"]) - p["elasticity"] * (smooth - smooth.mean()) + v + jumps + inflation

        for mid in mk:
            offset, share, lag = MARKET[cid][mid]
            r = _rng(cid, mid, "market")
            w = _ar1(r, n, 0.7, 0.035)
            lp = np.roll(log_region, lag)
            lp[:lag] = log_region[:lag]
            modal = np.clip(np.exp(lp + offset + w), 200, 15000)
            lo_s = r.uniform(*p["spread"], n)
            hi_s = r.uniform(p["spread"][0], p["spread"][1] * 1.15, n)
            arr = p["base_arr"] * share * np.exp(log_supply + r.normal(0, 0.18, n))
            closed = markets[mid]["closed_weekday"]
            dow = days.day_of_week.values
            if closed is not None:
                arr = np.where(dow == (closed + 1) % 7, arr * 1.35, arr)
            reported = r.random(n) > 0.02
            if closed is not None:
                reported &= dow != closed
            reported &= np.array([(d.month, d.day) not in HOLIDAYS for d in days])
            # one reporting outage of 4-8 days per year
            for year in range(days[0].year, days[-1].year + 1):
                start = r.integers(0, 330)
                length = r.integers(4, 9)
                idx = np.where(days.year == year)[0]
                if len(idx) > start + length:
                    reported[idx[start]: idx[start] + length] = False
            for i in np.where(reported)[0]:
                rows.append((cid, mid, days[i], round(modal[i] * (1 - lo_s[i]), -1), round(modal[i] * (1 + hi_s[i]), -1),
                             round(modal[i], -1), round(float(arr[i]), 1)))

    df = pd.DataFrame(rows, columns=["crop", "market", "date", "min", "max", "modal", "arrivals_t"])
    df = df[df["date"] <= pd.Timestamp(end)].reset_index(drop=True)
    return _to_agmarknet_format(df, catalog)


def _to_agmarknet_format(df: pd.DataFrame, catalog: dict) -> pd.DataFrame:
    """Write it the way a raw export looks, including the usual reporting problems."""
    r = _rng("raw-noise")
    crops = {c["id"]: c for c in catalog["crops"]}
    markets = {m["id"]: m for m in catalog["markets"]}
    out = pd.DataFrame({
        "State": catalog["state"],
        "District": df["market"].map(lambda m: markets[m]["district"]),
        "Market": df["market"].map(lambda m: markets[m]["en"]),
        "Commodity": df["crop"].map(lambda c: crops[c]["en"]),
        "Variety": df["crop"].map({"tomato": "Local", "onion": "Big", "banana": "Green"}),
        "Grade": "FAQ",
        "Arrival_Date": df["date"].dt.strftime("%d/%m/%Y"),
        "Min_Price": df["min"], "Max_Price": df["max"], "Modal_Price": df["modal"],
        "Arrivals_Tonnes": df["arrivals_t"],
    })
    n = len(out)
    # name variants (handled by the name-matching table)
    alt = r.random(n) < 0.08
    out.loc[alt, "Market"] = df.loc[alt, "market"].map(lambda m: markets[m]["aliases"][1].title())
    upper = r.random(n) < 0.05
    out.loc[upper, "Commodity"] = out.loc[upper, "Commodity"].str.upper()
    # swapped min/max
    sw = r.random(n) < 0.0015
    out.loc[sw, ["Min_Price", "Max_Price"]] = out.loc[sw, ["Max_Price", "Min_Price"]].values
    # price typed per kg instead of per quintal
    kg = r.random(n) < 0.0008
    out.loc[kg, ["Min_Price", "Max_Price", "Modal_Price"]] = (out.loc[kg, ["Min_Price", "Max_Price", "Modal_Price"]] / 100).round(1).values
    # duplicate submissions
    dup = out[r.random(n) < 0.003]
    out = pd.concat([out, dup], ignore_index=True)
    return out.sample(frac=1.0, random_state=7).reset_index(drop=True)
