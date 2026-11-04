"""Forecast Agent: baselines, SARIMA and LightGBM, honest backtest, conformal price ranges.

Windows (E = last data date):
    train        ... E-240d      models fitted here are scored on the calibration window
    calibration  E-240d .. E-120d  -> model selection + conformal quantiles for the backtest
    test         E-120d .. E      -> unseen months; models refitted up to E-120d, nothing tuned here
Production: models refitted on all data; ranges use the most recent (test-window) errors.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd

from pipeline.features import FEATURES, HORIZONS

MODELS = ["naive", "seasonal_naive", "moving_average", "sarima", "lightgbm"]
BASELINES = ["naive", "seasonal_naive", "moving_average"]
LABELS = {"naive": "Last price", "seasonal_naive": "Same as last week", "moving_average": "7-day average",
          "sarima": "SARIMA", "lightgbm": "LightGBM"}
WINDOW = 120
COVERAGE = 0.80
LGB_PARAMS = dict(objective="l1", learning_rate=0.03, n_estimators=450, num_leaves=15, min_child_samples=40,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=2)
H = len(HORIZONS)


# ---------------------------------------------------------------- per-model point forecasts
def baseline_forecasts(s: pd.DataFrame, origins: np.ndarray) -> dict[str, np.ndarray]:
    ff = s["modal_ff"].to_numpy()
    raw = s["modal"].to_numpy()
    out = {m: np.full((len(origins), H), np.nan) for m in BASELINES}
    for k, i in enumerate(origins):
        out["naive"][k] = ff[i]
        out["seasonal_naive"][k] = [ff[i + h - 7] if i + h - 7 >= 0 else ff[i] for h in HORIZONS]
        win = raw[max(0, i - 6): i + 1]
        out["moving_average"][k] = np.nanmean(win) if np.isfinite(win).any() else ff[i]
    return out


def _sarima_fit(y: np.ndarray):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 0, 1, 7), trend="n",
                      enforce_stationarity=False, enforce_invertibility=False)
        return mod.fit(disp=False, maxiter=60, method="lbfgs")


def sarima_forecasts(s: pd.DataFrame, origins: np.ndarray, fit_end: int) -> np.ndarray:
    """Fit on [fit_end-730, fit_end), then forecast 7 days from each origin with fixed parameters."""
    y = np.log(s["modal_ff"].to_numpy())
    out = np.full((len(origins), H), np.nan)
    start = max(0, fit_end - 730)
    try:
        res = _sarima_fit(y[start:fit_end])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            full = res.apply(y[start:])
            for k, i in enumerate(origins):
                j = i - start
                pred = full.get_prediction(start=j + 1, end=j + H, dynamic=True).predicted_mean
                out[k] = np.exp(pred)
    except Exception as exc:
        print(f"SARIMA failed for {s['crop'].iat[0]}/{s['market'].iat[0]}: {exc}")
    return out


def sarima_production(s: pd.DataFrame) -> np.ndarray | None:
    y = np.log(s["modal_ff"].to_numpy())[-730:]
    try:
        res = _sarima_fit(y)
        return np.exp(res.forecast(H))
    except Exception as exc:
        print(f"SARIMA production failed: {exc}")
        return None


def lgb_train(panel: pd.DataFrame, crop: str, end_date: pd.Timestamp | None) -> dict[int, lgb.LGBMRegressor]:
    d = panel[(panel["crop"] == crop) & panel["reported"]]
    if end_date is not None:
        d = d[d["date"] < end_date]
    models = {}
    for h in HORIZONS:
        dd = d.dropna(subset=[f"y_{h}"])
        if end_date is not None:
            dd = dd[dd["date"] + pd.Timedelta(days=h) < end_date]  # target must also be before the cut
        if len(dd) < 200:
            continue
        m = lgb.LGBMRegressor(**LGB_PARAMS)
        m.fit(dd[FEATURES], dd[f"y_{h}"], categorical_feature=["market_code"])
        models[h] = m
    return models


def lgb_forecasts(s: pd.DataFrame, origins: np.ndarray, models: dict) -> np.ndarray:
    out = np.full((len(origins), H), np.nan)
    if not models:
        return out
    X = s.iloc[origins][FEATURES]
    base = s["modal_ff"].to_numpy()[origins]
    for h, m in models.items():
        out[:, h - 1] = base * np.exp(m.predict(X))
    return out


# ---------------------------------------------------------------- evaluation helpers
def actuals(s: pd.DataFrame, origins: np.ndarray) -> np.ndarray:
    raw = s["modal"].to_numpy()
    n = len(raw)
    out = np.full((len(origins), H), np.nan)
    for k, i in enumerate(origins):
        for h in HORIZONS:
            if i + h < n:
                out[k, h - 1] = raw[i + h]
    return out


def scale(s: pd.DataFrame, origins: np.ndarray) -> np.ndarray:
    vol = s["vol_14"].to_numpy()[origins]
    vol = np.where(np.isfinite(vol), vol, np.nanmedian(s["vol_14"]))
    vol = np.maximum(vol, 0.01)
    return vol[:, None] * np.sqrt(np.array(HORIZONS))[None, :]


def mape(pred: np.ndarray, act: np.ndarray) -> float:
    ok = np.isfinite(pred) & np.isfinite(act)
    return float(np.mean(np.abs(pred[ok] - act[ok]) / act[ok]) * 100) if ok.any() else float("nan")


def conformal_q(scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-horizon lower/upper quantiles of normalised log errors (split conformal, finite-sample adjusted)."""
    lo, hi = np.zeros(H), np.zeros(H)
    a = (1 - COVERAGE) / 2
    for j in range(H):
        sc = scores[:, j]
        sc = sc[np.isfinite(sc)]
        if len(sc) < 20:
            lo[j], hi[j] = -1.6, 1.6
            continue
        n = len(sc)
        lo[j] = np.quantile(sc, max(0.0, a * (n + 1) / n - 1 / n), method="lower")
        hi[j] = np.quantile(sc, min(1.0, (1 - a) * (n + 1) / n), method="higher")
    return lo, hi


def direction_hits(pred: np.ndarray, act: np.ndarray, base: np.ndarray, min_move: float = 0.02) -> tuple[int, int]:
    hits = total = 0
    for k in range(len(base)):
        a = act[k][np.isfinite(act[k])]
        if not len(a) or not np.isfinite(pred[k]).all():
            continue
        move = a.mean() / base[k] - 1
        if abs(move) < min_move:
            continue
        total += 1
        hits += int(np.sign(pred[k].mean() / base[k] - 1) == np.sign(move))
    return hits, total


# ---------------------------------------------------------------- main entry
def run_forecasts(panel: pd.DataFrame, catalog: dict, log) -> tuple[dict, dict, dict]:
    """Returns (backtest report, production forecasts by series key, lgb production models by crop)."""
    end = panel["date"].max()
    test_start = end - pd.Timedelta(days=WINDOW)
    cal_start = test_start - pd.Timedelta(days=WINDOW)
    log.add("forecast_agent", "build_features", f"{len(panel)} feature rows; calibration {cal_start.date()}..{test_start.date()}, test {test_start.date()}..{end.date()}")

    lgb_cal = {c["id"]: lgb_train(panel, c["id"], cal_start) for c in catalog["crops"]}
    lgb_test = {c["id"]: lgb_train(panel, c["id"], test_start) for c in catalog["crops"]}
    lgb_prod = {c["id"]: lgb_train(panel, c["id"], None) for c in catalog["crops"]}
    log.add("forecast_agent", "run_models", "LightGBM trained per crop and horizon (calibration, test and production fits)")

    per_series = {}
    for (crop, market), s in panel.groupby(["crop", "market"], sort=False):
        s = s.reset_index(drop=True)
        dates = s["date"]
        rep = s["reported"].to_numpy()
        cal_o = np.where(rep & (dates >= cal_start).to_numpy() & (dates < test_start).to_numpy())[0]
        test_o = np.where(rep & (dates >= test_start).to_numpy())[0]
        if len(cal_o) < 30 or len(test_o) < 20 or len(s) < 400:
            per_series[(crop, market)] = None
            continue
        res = {}
        for name, origins, fit_end_date, lgbm in (("cal", cal_o, cal_start, lgb_cal[crop]), ("test", test_o, test_start, lgb_test[crop])):
            preds = baseline_forecasts(s, origins)
            fit_end = int(np.searchsorted(dates.to_numpy(), np.datetime64(fit_end_date)))
            preds["sarima"] = sarima_forecasts(s, origins, fit_end)
            preds["lightgbm"] = lgb_forecasts(s, origins, lgbm)
            res[name] = {"preds": preds, "act": actuals(s, origins), "scale": scale(s, origins),
                         "base": s["modal_ff"].to_numpy()[origins]}
        per_series[(crop, market)] = res
    log.add("forecast_agent", "run_baselines", f"backtest done for {sum(v is not None for v in per_series.values())} series")

    # conformal quantiles per crop and model, from calibration-window errors
    def scores(window: str, crop: str, model: str) -> np.ndarray:
        rows = []
        for (c, _m), r in per_series.items():
            if r is None or c != crop:
                continue
            w = r[window]
            rows.append(np.log(w["act"] / w["preds"][model]) / w["scale"])
        return np.vstack(rows) if rows else np.empty((0, H))

    crops = sorted({c for c, _ in per_series})
    q_cal = {(c, m): conformal_q(scores("cal", c, m)) for c in crops for m in MODELS}
    q_recent = {(c, m): conformal_q(scores("test", c, m)) for c in crops for m in MODELS}

    series_rows, all_pred, all_act, all_lo, all_hi = [], {m: [] for m in MODELS + ["selected"]}, [], [], []
    dir_hits = dir_total = 0
    horizon_err = {m: [[] for _ in HORIZONS] for m in MODELS + ["selected"]}
    selected_prod = {}
    for (crop, market), r in per_series.items():
        if r is None:
            continue
        cal_mape = {m: mape(r["cal"]["preds"][m], r["cal"]["act"]) for m in MODELS}
        cal_mape = {m: v for m, v in cal_mape.items() if np.isfinite(v)}
        sel = min(cal_mape, key=cal_mape.get)
        t = r["test"]
        test_mape = {m: mape(t["preds"][m], t["act"]) for m in MODELS}
        sel_pred = t["preds"][sel]
        qlo, qhi = q_cal[(crop, sel)]
        lo = sel_pred * np.exp(qlo[None, :] * t["scale"])
        hi = sel_pred * np.exp(qhi[None, :] * t["scale"])
        ok = np.isfinite(t["act"])
        cov = float(np.mean((t["act"][ok] >= lo[ok]) & (t["act"][ok] <= hi[ok])))
        h_, n_ = direction_hits(sel_pred, t["act"], t["base"])
        dir_hits += h_
        dir_total += n_
        best_base = min(BASELINES, key=lambda m: test_mape[m])
        sel_test = mape(sel_pred, t["act"])
        # model for today's forecast: lowest error over the last 240 days (calibration + test windows)
        c = r["cal"]
        recent = {m: mape(np.vstack([c["preds"][m], t["preds"][m]]), np.vstack([c["act"], t["act"]])) for m in MODELS}
        recent = {m: v for m, v in recent.items() if np.isfinite(v)}
        selected_prod[(crop, market)] = min(recent, key=recent.get)
        series_rows.append({"crop": crop, "market": market, "n_test": int(len(t["base"])),
                            "production_model": selected_prod[(crop, market)],
                            "mape": {**{m: round(v, 2) for m, v in test_mape.items() if np.isfinite(v)}, "selected": round(sel_test, 2)},
                            "selected": sel, "coverage": round(cov, 3),
                            "direction_accuracy": round(h_ / n_, 3) if n_ else None,
                            "improvement_pct": round((test_mape[best_base] - sel_test) / test_mape[best_base] * 100, 1)})
        for m in MODELS:
            all_pred[m].append(t["preds"][m])
        all_pred["selected"].append(sel_pred)
        all_act.append(t["act"])
        all_lo.append(lo)
        all_hi.append(hi)

    act = np.vstack(all_act)
    overall = {m: round(mape(np.vstack(all_pred[m]), act), 2) for m in MODELS + ["selected"]}
    by_h = []
    for j, h in enumerate(HORIZONS):
        by_h.append({"h": h, "mape": {m: round(mape(np.vstack(all_pred[m])[:, j], act[:, j]), 2) for m in MODELS + ["selected"]}})
    lo_all, hi_all = np.vstack(all_lo), np.vstack(all_hi)
    ok = np.isfinite(act)
    coverage = float(np.mean((act[ok] >= lo_all[ok]) & (act[ok] <= hi_all[ok])))
    best_baseline = min(BASELINES, key=lambda m: overall[m])
    improvement = (overall[best_baseline] - overall["selected"]) / overall[best_baseline] * 100
    direction = dir_hits / dir_total if dir_total else 0.0
    log.add("forecast_agent", "make_range", f"test coverage of 80% ranges: {coverage:.1%}; selected MAPE {overall['selected']} vs best baseline ({best_baseline}) {overall[best_baseline]}")

    report = {
        "test_window": {"start": str(test_start.date()), "end": str(end.date()), "days": WINDOW},
        "calibration_window": {"start": str(cal_start.date()), "end": str(test_start.date()), "days": WINDOW},
        "model_labels": LABELS,
        "overall": {"mape": overall, "best_baseline": best_baseline, "improvement_pct": round(improvement, 1),
                    "coverage": round(coverage, 3), "direction_accuracy": round(direction, 3), "direction_n": dir_total},
        "by_horizon": by_h,
        "series": series_rows,
        "selection_counts": pd.Series([r["selected"] for r in series_rows]).value_counts().to_dict(),
        "production_counts": pd.Series([r["production_model"] for r in series_rows]).value_counts().to_dict(),
        "selection_note": ("'selected' = model chosen on the calibration window and scored on the unseen test window; "
                           "'production_model' = model used for today's forecast, chosen on the last 240 days."),
    }

    production = {}
    for (crop, market), s in panel.groupby(["crop", "market"], sort=False):
        s = s.reset_index(drop=True)
        model = selected_prod.get((crop, market))
        if model is None:
            production[(crop, market)] = None
            continue
        last = len(s) - 1
        origin = np.array([last])
        if model in BASELINES:
            point = baseline_forecasts(s, origin)[model][0]
        elif model == "sarima":
            point = sarima_production(s)
            if point is None:
                model, point = "naive", baseline_forecasts(s, origin)["naive"][0]
        else:
            point = lgb_forecasts(s, origin, lgb_prod[crop])[0]
        sc = scale(s, origin)[0]
        qlo, qhi = q_recent[(crop, model)]
        production[(crop, market)] = {"model": model, "point": point, "lo": point * np.exp(qlo * sc),
                                      "hi": point * np.exp(qhi * sc), "origin_row": s.iloc[last]}
    log.add("forecast_agent", "run_models", f"production forecasts for {sum(v is not None for v in production.values())} series")
    return report, production, lgb_prod
