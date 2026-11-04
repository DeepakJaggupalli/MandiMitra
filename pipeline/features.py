"""Feature building for the Forecast Agent (only information available on day t is used)."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = list(range(1, 8))

GROUPS = {
    "arrivals": ["arr_chg_7", "arr_ratio_28", "arr_1", "arr_l"],
    "momentum": ["ret_1", "ret_3", "ret_7", "down_days_5", "up_days_5"],
    "level": ["ma7_gap", "ma30_gap", "ma90_gap", "ret_14", "ret_28", "yoy_gap"],
    "season": ["doy_sin", "doy_cos", "month", "harvest", "lean"],
    "region": ["region_gap", "region_ret_7"],
    "weather": ["rain_7", "rain_30", "tmax_7"],
    "volatility": ["vol_14", "spread"],
    "market": ["market_code", "dow", "days_since_report"],
}
FEATURES = [f for g in GROUPS.values() for f in g]


def _count_moves(reported: pd.Series, n: int = 5) -> tuple[pd.Series, pd.Series]:
    """Down / up moves over the last n market days (reported days only), carried to calendar days."""
    s = reported.dropna()
    d = s.diff()
    down = (d < 0).astype(float).rolling(n, min_periods=n).sum()
    up = (d > 0).astype(float).rolling(n, min_periods=n).sum()
    return down.reindex(reported.index).ffill(), up.reindex(reported.index).ffill()


def build_panel(clean_df: pd.DataFrame, weather: pd.DataFrame | None, catalog: dict) -> pd.DataFrame:
    crops = {c["id"]: c for c in catalog["crops"]}
    market_code = {m["id"]: i for i, m in enumerate(catalog["markets"])}
    w = None
    if weather is not None and not weather.empty:
        w = weather.set_index(["market", "date"]).sort_index()

    frames = []
    for (crop, market), s in clean_df.groupby(["crop", "market"]):
        s = s.set_index("date").sort_index()
        idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
        p = s.reindex(idx)
        p.index.name = "date"
        p["crop"], p["market"] = crop, market
        p["reported"] = p["modal"].notna()
        p["modal_ff"] = p["modal"].ffill()
        lp = np.log(p["modal_ff"])
        p["lp"] = lp
        for k in (1, 3, 7, 14, 28):
            p[f"ret_{k}"] = lp.diff(k)
        for k in (7, 30, 90):
            p[f"ma{k}_gap"] = lp - np.log(p["modal_ff"].rolling(k, min_periods=max(3, k // 3)).mean())
        p["yoy_gap"] = lp - lp.shift(365)
        p["vol_14"] = p["ret_1"].rolling(14, min_periods=7).std()
        p["down_days_5"], p["up_days_5"] = _count_moves(p["modal"])
        arr = p["arrivals_t"]
        arr7 = arr.rolling(7, min_periods=3).mean()
        arr28 = arr.rolling(28, min_periods=10).mean()
        p["arr_l"] = np.log1p(arr7)
        p["arr_chg_7"] = np.log(arr7 / arr7.shift(7))
        p["arr_ratio_28"] = np.log(arr7 / arr28)
        p["arr_1"] = np.log(arr.ffill(limit=3) / arr28)
        p["spread"] = (p["max"].ffill() - p["min"].ffill()) / p["modal_ff"]
        doy = idx.day_of_year.values
        p["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
        p["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
        p["month"] = idx.month
        p["harvest"] = idx.month.isin(crops[crop]["peak_months"]).astype(int)
        p["lean"] = idx.month.isin(crops[crop]["lean_months"]).astype(int)
        p["dow"] = idx.day_of_week
        p["market_code"] = market_code[market]
        grp = p["reported"].cumsum()
        p["days_since_report"] = p.groupby(grp).cumcount().astype(float)
        if w is not None and market in w.index.get_level_values(0):
            mw = w.loc[market].reindex(idx)
            p["rain_7"] = mw["rain_mm"].rolling(7, min_periods=4).sum()
            p["rain_30"] = mw["rain_mm"].rolling(30, min_periods=15).sum()
            p["tmax_7"] = mw["tmax_c"].rolling(7, min_periods=4).mean()
        else:
            p["rain_7"] = p["rain_30"] = p["tmax_7"] = np.nan
        for h in HORIZONS:
            p[f"y_{h}"] = np.log(p["modal"].shift(-h)) - lp  # NaN when day t+h was not reported
        frames.append(p.reset_index())

    panel = pd.concat(frames, ignore_index=True)
    region = panel.groupby(["crop", "date"])["lp"].mean().rename("region_lp")
    panel = panel.join(region, on=["crop", "date"])
    panel["region_gap"] = panel["lp"] - panel["region_lp"]
    rr = panel[["crop", "date", "region_lp"]].drop_duplicates().sort_values(["crop", "date"])
    rr["region_ret_7"] = rr.groupby("crop")["region_lp"].diff(7)
    panel = panel.merge(rr[["crop", "date", "region_ret_7"]], on=["crop", "date"], how="left")
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel.sort_values(["crop", "market", "date"]).reset_index(drop=True)
