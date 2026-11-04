"""Turn model output into plain Telugu / English: top-3 reasons (TreeSHAP), confidence, advice."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.features import FEATURES, GROUPS

MONTHS_TE = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జులై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _pct(logv: float) -> int:
    return int(round(abs(np.expm1(logv)) * 100))


def _fmt_rs(v: float) -> str:
    v = int(round(v))
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if v < 0 else "") + s


def reason_text(group: str, row: pd.Series, crop: dict) -> tuple[str, str] | None:
    g = lambda k: row.get(k, np.nan)  # noqa: E731
    if group == "arrivals":
        v = g("arr_chg_7")
        if not np.isfinite(v):
            return None
        p = _pct(v)
        if p < 5:
            return "Arrivals are steady compared with last week", "సరుకు రాక గత వారంతో పోలిస్తే స్థిరంగా ఉంది"
        if v > 0:
            return f"Arrivals up {p}% from last week", f"సరుకు రాక గత వారం కంటే {p}% పెరిగింది"
        return f"Arrivals down {p}% from last week", f"సరుకు రాక గత వారం కంటే {p}% తగ్గింది"
    if group == "momentum":
        down, up = g("down_days_5"), g("up_days_5")
        if np.isfinite(down) and down >= 3:
            d = int(down)
            return f"Price fell on {d} of the last 5 market days", f"గత 5 మార్కెట్ రోజుల్లో {d} రోజులు ధర తగ్గింది"
        if np.isfinite(up) and up >= 3:
            d = int(up)
            return f"Price rose on {d} of the last 5 market days", f"గత 5 మార్కెట్ రోజుల్లో {d} రోజులు ధర పెరిగింది"
        v = g("ret_7")
        if not np.isfinite(v):
            return None
        p = _pct(v)
        if p < 3:
            return "Price was steady over the last week", "గత వారం ధర స్థిరంగా ఉంది"
        word_en, word_te = ("rose", "పెరిగింది") if v > 0 else ("fell", "తగ్గింది")
        return f"Price {word_en} {p}% in the last week", f"గత వారంలో ధర {p}% {word_te}"
    if group == "level":
        v = g("ma30_gap")
        if not np.isfinite(v):
            return None
        p = _pct(v)
        if p < 4:
            return "Price is close to its 30-day average", "ధర 30 రోజుల సగటుకు దగ్గరగా ఉంది"
        if v > 0:
            return f"Price is {p}% above its 30-day average", f"ధర 30 రోజుల సగటు కంటే {p}% ఎక్కువగా ఉంది"
        return f"Price is {p}% below its 30-day average", f"ధర 30 రోజుల సగటు కంటే {p}% తక్కువగా ఉంది"
    if group == "season":
        m = int(g("month"))
        if g("harvest") == 1:
            return "Peak harvest season in the region, so supply is high", "ఈ ప్రాంతంలో పంట కోత సీజన్, సరుకు ఎక్కువగా వస్తుంది"
        if g("lean") == 1:
            return "Lean season, supply is usually low", "సరుకు సాధారణంగా తక్కువగా ఉండే సీజన్"
        return f"Usual seasonal pattern for {MONTHS_EN[m - 1]}", f"{MONTHS_TE[m - 1]} నెల సాధారణ సీజన్ ధోరణి"
    if group == "region":
        v = g("region_gap")
        if not np.isfinite(v):
            return None
        p = _pct(v)
        if p < 3:
            return "Price is in line with nearby markets", "ధర సమీప మార్కెట్లతో సమానంగా ఉంది"
        if v > 0:
            return f"This market is {p}% above the average of nearby markets", f"ఈ మార్కెట్ ధర సమీప మార్కెట్ల సగటు కంటే {p}% ఎక్కువ"
        return f"This market is {p}% below the average of nearby markets", f"ఈ మార్కెట్ ధర సమీప మార్కెట్ల సగటు కంటే {p}% తక్కువ"
    if group == "weather":
        r = g("rain_7")
        if not np.isfinite(r):
            return None
        mm = int(round(r))
        if mm >= 25:
            return f"Heavy rain in the last week ({mm} mm) can cut supply", f"గత వారం భారీ వర్షం ({mm} మి.మీ.) వల్ల సరుకు తగ్గవచ్చు"
        if mm >= 5:
            return f"Some rain in the last week ({mm} mm)", f"గత వారం కొంత వర్షం పడింది ({mm} మి.మీ.)"
        return "Dry weather in the last week", "గత వారం వర్షం లేదు"
    if group == "volatility":
        return "Prices have been unstable in the last 2 weeks", "గత 2 వారాలుగా ధరలు ఒడిదుడుకులుగా ఉన్నాయి"
    return None


def top_reasons(models: dict, row: pd.Series, crop: dict, k: int = 3) -> list[dict]:
    if not models:
        return []
    X = pd.DataFrame([pd.to_numeric(row[FEATURES], errors="coerce").astype(float).values], columns=FEATURES)
    X["market_code"] = X["market_code"].astype(int)
    contrib = np.mean([m.predict(X, pred_contrib=True)[0][:-1] for m in models.values()], axis=0)
    by_feature = dict(zip(FEATURES, contrib))
    groups = {g: float(sum(by_feature[f] for f in fs)) for g, fs in GROUPS.items() if g != "market"}
    total = sum(abs(v) for v in groups.values()) or 1.0
    out = []
    for g, v in sorted(groups.items(), key=lambda kv: -abs(kv[1])):
        txt = reason_text(g, row, crop)
        if txt is None:
            continue
        out.append({"key": g, "en": txt[0], "te": txt[1], "effect": "up" if v > 0 else "down", "weight": round(abs(v) / total, 3)})
        if len(out) == k:
            break
    return out


CONF_ORDER = ["low", "medium", "high"]


def confidence(point7: float, lo7: float, hi7: float, notes_in: list[str]) -> tuple[str, list[dict]]:
    width = (hi7 - lo7) / point7 if point7 else 1.0
    level = 2 if width < 0.30 else 1 if width < 0.65 else 0
    notes = []
    texts = {
        "wide": ("The expected range is wide", "అంచనా పరిధి విస్తృతంగా ఉంది"),
        "anomaly": ("Unusual market movement this week", "ఈ వారం మార్కెట్‌లో అసాధారణ కదలిక ఉంది"),
        "stale": ("The latest price is a few days old", "తాజా ధర కొన్ని రోజుల క్రితంది"),
        "missing": ("Some recent market days were not reported", "ఇటీవల కొన్ని మార్కెట్ రోజుల ధరలు నమోదు కాలేదు"),
        "thin": ("Less than a year of history for this market", "ఈ మార్కెట్‌కు ఏడాది కంటే తక్కువ చరిత్ర ఉంది"),
    }
    if level == 0:
        notes.append("wide")
    for n in notes_in:
        level = max(0, level - 1)
        notes.append(n)
    return CONF_ORDER[level], [{"key": n, "en": texts[n][0], "te": texts[n][1]} for n in notes]


def advice(last: float, points: list[dict], conf: str, shelf_life: int) -> dict:
    usable = [p for p in points if p["h"] <= max(1, shelf_life)]
    best = max(usable, key=lambda p: p["point"])
    gain = best["point"] / last - 1
    mean_all = float(np.mean([p["point"] for p in points]))
    end_en, end_te = " The decision is yours.", " నిర్ణయం మీదే."
    if conf == "low":
        return {"action": "either",
                "en": "This week's forecast is uncertain. Selling in parts can reduce your risk." + end_en,
                "te": "ఈ వారం అంచనా అనిశ్చితంగా ఉంది. విడతలుగా అమ్మితే నష్ట భయం తగ్గుతుంది." + end_te}
    if gain > 0.05 and best["lo"] > last * 0.97:
        p, d = int(round(gain * 100)), best["h"]
        return {"action": "wait",
                "en": f"Prices may rise about {p}% in the next {d} days. If your produce can wait, waiting may help." + end_en,
                "te": f"వచ్చే {d} రోజుల్లో ధర సుమారు {p}% పెరగవచ్చు. మీ సరుకు నిల్వ ఉండగలిగితే ఆగడం మంచిది కావచ్చు." + end_te}
    if mean_all < last * 0.97:
        return {"action": "sell_now",
                "en": "Prices are likely to soften this week. Selling soon looks better." + end_en,
                "te": "ఈ వారం ధరలు తగ్గే అవకాశం ఉంది. త్వరగా అమ్మడం మంచిది." + end_te}
    return {"action": "either",
            "en": "Prices look steady this week. Sell when it suits you." + end_en,
            "te": "ఈ వారం ధరలు స్థిరంగా ఉండే అవకాశం ఉంది. మీకు అనుకూలమైనప్పుడు అమ్మండి." + end_te}
