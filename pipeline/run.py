"""Daily pipeline: Data Agent -> Forecast Agent -> unusual-move drafts. Writes data/processed/*.json.

Usage:
    python -m pipeline.run                    # auto: real data if present, else simulated
    python -m pipeline.run --source real      # fail if no real data
    python -m pipeline.run --history          # pull full history from data.gov.in (needs DATA_GOV_IN_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from pipeline.anomalies import detect
from pipeline.clean import clean
from pipeline.common import PROCESSED, RAW, RunLog, load_catalog, now_iso, write_json
from pipeline.explain import advice, confidence, top_reasons
from pipeline.features import build_panel
from pipeline.forecast import LABELS, run_forecasts
from pipeline.sources.agmarknet import RAW_COLS, load_real, map_columns
from pipeline.sources.simulate import SIM_START, simulate
from pipeline.sources.weather import fetch_weather

SOURCES = {
    "AGMARKNET": {"code": "AGMARKNET", "label_en": "AGMARKNET", "label_te": "అగ్‌మార్క్‌నెట్", "is_simulated": False},
    "SIMULATED": {"code": "SIMULATED", "label_en": "Sample data (simulated, AGMARKNET format)",
                  "label_te": "నమూనా సమాచారం (అనుకరణ, అగ్‌మార్క్‌నెట్ ఫార్మాట్)", "is_simulated": True},
}


def r10(v: float) -> int:
    return int(round(float(v) / 10.0) * 10)


def ist_today():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def build_forecast_json(key, prod, panel_s, crop_cfg, as_of_global, events_recent, lgb_models) -> dict:
    crop, market = key
    base = {"crop": crop, "market": market}
    not_avail = {**base, "available": False,
                 "reason_en": "Not enough recent data for a reliable forecast at this market.",
                 "reason_te": "ఈ మార్కెట్‌లో నమ్మకమైన అంచనాకు సరిపడా తాజా సమాచారం లేదు."}
    if prod is None:
        return not_avail
    row = prod["origin_row"]
    last_date = row["date"].date()
    if (as_of_global - last_date).days > 7:
        return not_avail
    last = float(row["modal_ff"])
    points = [{"date": str(last_date + timedelta(days=h)), "h": h, "point": r10(p), "lo": r10(min(lo, p)), "hi": r10(max(hi, p))}
              for h, (p, lo, hi) in enumerate(zip(prod["point"], prod["lo"], prod["hi"]), start=1)]
    reported = panel_s[panel_s["reported"]]
    recent30 = panel_s[panel_s["date"] > row["date"] - pd.Timedelta(days=30)]
    notes = []
    anomaly = next((e for e in events_recent if e["crop"] == crop and e["market"] == market
                    and (last_date - datetime.fromisoformat(e["date"]).date()).days <= 7), None)
    if anomaly:
        notes.append("anomaly")
    if (as_of_global - last_date).days > 3:
        notes.append("stale")
    if recent30["reported"].mean() < 0.75:
        notes.append("missing")
    if len(reported) < 365:
        notes.append("thin")
    p7 = points[-1]
    conf, conf_notes = confidence(p7["point"], p7["lo"], p7["hi"], notes)
    mean_pt = float(np.mean([p["point"] for p in points]))
    direction = "up" if mean_pt > last * 1.03 else "down" if mean_pt < last * 0.97 else "flat"
    return {**base, "available": True, "as_of": str(last_date), "last_price": r10(last),
            "model": prod["model"], "model_label": LABELS[prod["model"]],
            "confidence": conf, "confidence_notes": conf_notes, "points": points,
            "summary": {"point_mean": r10(mean_pt), "lo": min(p["lo"] for p in points), "hi": max(p["hi"] for p in points), "direction": direction},
            "reasons": top_reasons(lgb_models, row, crop_cfg),
            "advice": advice(last, points, conf, crop_cfg["shelf_life_days"]),
            "anomaly": {k: anomaly[k] for k in ("type", "date", "en", "te")} if anomaly else None}


def criteria(acc: dict, history: list[dict]) -> list[dict]:
    o = acc["overall"]
    last30 = [h for h in history if h["date"] >= str(ist_today() - timedelta(days=30))]
    ok_days = len({h["date"] for h in last30 if h["status"] == "ok"})
    tracked = len({h["date"] for h in last30}) or 1
    rel = ok_days / tracked
    return [
        {"key": "pipeline", "name_en": "Data pipeline reliability", "name_te": "డేటా పైప్‌లైన్ నమ్మకం",
         "target": "Daily update succeeds on at least 95% of days", "value": f"{ok_days} of {tracked} tracked days ({rel:.0%})", "passed": rel >= 0.95},
        {"key": "accuracy", "name_en": "Forecast accuracy vs simple baseline", "name_te": "సాధారణ పద్ధతితో పోలిస్తే అంచనా ఖచ్చితత్వం",
         "target": "At least 10% lower MAPE on unseen months",
         "value": f"{o['improvement_pct']}% lower MAPE ({o['mape']['selected']}% vs {o['mape'][o['best_baseline']]}%)", "passed": o["improvement_pct"] >= 10},
        {"key": "coverage", "name_en": "Honest price range", "name_te": "నిజాయితీ గల ధర పరిధి",
         "target": "About 80% of actual prices inside the range", "value": f"{o['coverage']:.0%}", "passed": 0.75 <= o["coverage"] <= 0.88},
        {"key": "direction", "name_en": "Direction of movement (up / down)", "name_te": "ధర దిశ (పెరుగుదల / తగ్గుదల)",
         "target": "Correct at least 6 times in 10", "value": f"{o['direction_accuracy']:.0%} of {o['direction_n']} clear moves", "passed": o["direction_accuracy"] >= 0.6},
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["auto", "real", "simulated"], default="auto")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--end", help="last data date (default: yesterday, IST)")
    args = ap.parse_args(argv)
    t0 = time.time()
    log = RunLog()
    catalog = load_catalog()
    end = datetime.fromisoformat(args.end).date() if args.end else ist_today() - timedelta(days=1)
    log.add("data_agent", "start", f"daily run, source={args.source}, data up to {end}")

    weather = fetch_weather(catalog["markets"], SIM_START, end, log)
    real = load_real(catalog, log, history=args.history) if args.source != "simulated" else pd.DataFrame(columns=RAW_COLS)
    if args.source == "real" and real.empty:
        log.add("data_agent", "fetch_agmarknet", "no real data found", level="error")
        return 2
    if not real.empty:
        source = SOURCES["AGMARKNET"]
        raw = real
        end = min(end, real["date"].max().date())
    else:
        source = SOURCES["SIMULATED"]
        sim = simulate(catalog, end, weather)
        RAW.mkdir(parents=True, exist_ok=True)
        sim.to_csv(RAW / "simulated_agmarknet.csv", index=False)
        raw = map_columns(sim)
        raw["source"] = "SIMULATED"
        log.add("data_agent", "fetch_agmarknet", f"no real data configured; generated {len(sim)} simulated AGMARKNET-format rows")

    clean_df, quality = clean(raw, catalog, end, log)
    as_of = clean_df["date"].max().date()
    panel = build_panel(clean_df, weather, catalog)
    acc, production, lgb_prod = run_forecasts(panel, catalog, log)
    anomalies = detect(panel, catalog, log)

    crops = {c["id"]: c for c in catalog["crops"]}
    forecasts = {}
    for (crop, market), s in panel.groupby(["crop", "market"]):
        forecasts[f"{crop}|{market}"] = build_forecast_json((crop, market), production.get((crop, market)), s, crops[crop],
                                                            as_of, anomalies["recent"], lgb_prod.get(crop, {}))
    log.add("forecast_agent", "explain_forecast", "top-3 reasons written for every available forecast (LightGBM TreeSHAP)")
    log.add("alert_agent", "detect_unusual", f"{len(anomalies['recent'])} big-move warnings drafted for officer review")

    prices = {}
    for (crop, market), s in clean_df.groupby(["crop", "market"]):
        s = s.sort_values("date")
        prices[f"{crop}|{market}"] = {
            "dates": s["date"].dt.strftime("%Y-%m-%d").tolist(),
            "min": s["min"].astype(int).tolist(), "max": s["max"].astype(int).tolist(), "modal": s["modal"].astype(int).tolist(),
            "arr": [None if pd.isna(v) else round(float(v), 1) for v in s["arrivals_t"]],
        }

    hist_path = PROCESSED / "run_history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    history = [h for h in history if h["date"] != str(ist_today())] + [{"date": str(ist_today()), "status": "ok", "source": source["code"], "data_as_of": str(as_of)}]
    history = history[-180:]
    generated = now_iso()
    acc["generated_at"] = generated
    acc["criteria"] = criteria(acc, history)
    quality.update({"generated_at": generated, "source": source})
    log.add("data_agent", "done", f"pipeline finished in {time.time() - t0:.0f}s")
    meta = {"generated_at": generated, "data_as_of": str(as_of), "source": source, "is_simulated": source["is_simulated"],
            "crops": [{k: c[k] for k in ("id", "en", "te", "shelf_life_days", "markets")} for c in catalog["crops"]],
            "markets": [{k: m[k] for k in ("id", "en", "te", "district", "lat", "lon")} for m in catalog["markets"]],
            "pipeline_log": log.entries, "weather_rows": int(len(weather))}

    write_json(PROCESSED / "prices.json", prices)
    write_json(PROCESSED / "forecasts.json", forecasts)
    write_json(PROCESSED / "accuracy.json", acc)
    write_json(PROCESSED / "quality.json", quality)
    write_json(PROCESSED / "anomalies.json", anomalies)
    write_json(PROCESSED / "meta.json", meta)
    write_json(hist_path, history)
    print(json.dumps(acc["overall"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
