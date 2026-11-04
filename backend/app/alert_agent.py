"""Agent 4, Alert Agent: target-price checks, big-move warnings and the weekly bulletin.

Target-price alerts go straight to the farmer (checked on the phone). Big-move
warnings and the weekly bulletin are only drafts until an extension officer approves them.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend.app.assistant import fd, rs
from backend.app.db import DB, now
from backend.app.store import Store, trend_label

CONF_TE = {"high": "ఎక్కువ", "medium": "మధ్యస్థం", "low": "తక్కువ"}


def check_targets(store: Store, alerts: list[dict]) -> list[dict]:
    out = []
    for a in alerts[:50]:
        last = store.latest(a.get("crop", ""), a.get("market", "")) if store.has(a.get("crop", ""), a.get("market", "")) else None
        if not last:
            out.append({"id": a.get("id"), "triggered": False, "current": None, "date": None})
            continue
        target = float(a.get("target") or 0)
        hit = last["modal"] >= target if a.get("direction", "above") == "above" else last["modal"] <= target
        out.append({"id": a.get("id"), "triggered": bool(hit), "current": last["modal"], "date": last["date"]})
    return out


def sync_warnings(db: DB, store: Store) -> int:
    """Draft a pending warning for every recent unusual move that is not in the review queue yet."""
    added = 0
    existing = {r["id"] for r in db.query("SELECT id FROM warnings")}
    for e in store.anomalies.get("recent", []):
        if e["id"] in existing:
            continue
        db.execute("INSERT INTO warnings (id, crop, market, type, date, magnitude, en, te, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (e["id"], e["crop"], e["market"], e["type"], e["date"], e["magnitude"], e["en"], e["te"], "pending", now()))
        added += 1
    if added:
        db.audit("alert_agent", "draft_alert", f"{added} big-move warnings drafted for officer review")
    return added


def draft_weekly_bulletin(store: Store, week_start: date | None = None) -> dict:
    as_of = store.data_as_of
    week_start = week_start or (as_of - timedelta(days=as_of.weekday()))
    en_lines, te_lines = [], []
    for c in store.catalog["crops"]:
        rows = store.latest_rows(c["id"])
        if not rows:
            continue
        hub = c["markets"][0]
        hub_row = next((r for r in rows if r["market"] == hub), rows[0])
        hub_m = store.markets[hub_row["market"]]
        top = max(rows, key=lambda r: r["modal"])
        top_m = store.markets[top["market"]]
        ch = hub_row["change_7d_pct"] or 0.0
        lab = trend_label(ch)
        word_en = {"rising": f"up {abs(ch):.1f}% this week", "falling": f"down {abs(ch):.1f}% this week", "steady": "steady this week"}[lab]
        word_te = {"rising": f"ఈ వారం {abs(ch):.1f}% పెరిగింది", "falling": f"ఈ వారం {abs(ch):.1f}% తగ్గింది", "steady": "ఈ వారం స్థిరంగా ఉంది"}[lab]
        en = f"{c['en']}: {hub_m['en']} {rs(hub_row['modal'])} per quintal ({word_en}). Highest today: {top_m['en']} {rs(top['modal'])}."
        te = f"{c['te']}: {hub_m['te']}లో క్వింటాల్ {rs(hub_row['modal'])} ({word_te}). ఈ రోజు ఎక్కువ ధర: {top_m['te']} {rs(top['modal'])}."
        fc = store.forecast(c["id"], hub_row["market"])
        if fc and fc.get("available"):
            s = fc["summary"]
            en += f" Next 7 days at {hub_m['en']}: likely {rs(s['lo'])} to {rs(s['hi'])} ({fc['confidence']} confidence)."
            te += f" వచ్చే 7 రోజులు {hub_m['te']}లో: {rs(s['lo'])} నుండి {rs(s['hi'])} మధ్య (నమ్మకం: {CONF_TE[fc['confidence']]})."
            if fc["reasons"]:
                en += f" Why: {fc['reasons'][0]['en']}."
                te += f" కారణం: {fc['reasons'][0]['te']}."
        en_lines.append(en)
        te_lines.append(te)
    moves = store.anomalies.get("recent", [])[:5]
    if moves:
        en_lines.append("Unusual moves: " + " ".join(m["en"] for m in moves))
        te_lines.append("అసాధారణ కదలికలు: " + " ".join(m["te"] for m in moves))
    src_en, src_te = store.source["label_en"], store.source["label_te"]
    en_lines.append(f"Data: {src_en}, up to {fd(str(as_of))}. This is a guide, not a guaranteed price. The decision is yours.")
    te_lines.append(f"సమాచారం: {src_te}, {fd(str(as_of), True)} వరకు. ఇది ఒక సూచన మాత్రమే, హామీ ధర కాదు. నిర్ణయం మీదే.")
    return {"week_start": str(week_start),
            "title_en": f"MandiMitra weekly market bulletin, week of {fd(str(week_start))}",
            "title_te": f"మండిమిత్ర వారపు మార్కెట్ బులెటిన్, {fd(str(week_start), True)} వారం",
            "body_en": "\n\n".join(en_lines), "body_te": "\n\n".join(te_lines)}
