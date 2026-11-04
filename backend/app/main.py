"""MandiMitra API (FastAPI). Runs locally with uvicorn and on Vercel as a Python function."""
from __future__ import annotations

import json
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from backend.app import settings
from backend.app.alert_agent import check_targets, draft_weekly_bulletin, sync_warnings
from backend.app.assistant import ask, numbers
from backend.app.auth import authenticate, current_user, make_token, require
from backend.app.db import get_db, now
from backend.app.netprice import compare_markets
from backend.app.store import get_store

app = FastAPI(title="MandiMitra API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

CACHEABLE = ("/api/meta", "/api/places", "/api/prices", "/api/forecast", "/api/accuracy", "/api/assistant/eval")


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200 and request.url.path.startswith(CACHEABLE):
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=1800, stale-while-revalidate=86400"
    return response


def _crop_market(crop: str, market: str | None = None):
    s = get_store()
    if crop not in s.crops:
        raise HTTPException(404, f"Unknown crop '{crop}'")
    if market is not None and not s.has(crop, market):
        raise HTTPException(404, f"No data for {crop} at '{market}'")
    return s


# ------------------------------------------------------------------ public data
@app.get("/api/health")
def health():
    s = get_store()
    return {"status": "ok", "data_as_of": s.meta["data_as_of"], "db": get_db().kind, "llm": settings.LLM_ENABLED}


@app.get("/api/meta")
def meta():
    s = get_store()
    m = s.meta
    return {"app": "MandiMitra", "version": app.version, "generated_at": m["generated_at"], "data_as_of": m["data_as_of"],
            "source": m["source"], "is_simulated": m["is_simulated"], "llm_enabled": settings.LLM_ENABLED,
            "crops": m["crops"], "markets": m["markets"]}


@app.get("/api/places")
def places():
    return {"rows": get_store().places}


@app.get("/api/prices/latest")
def prices_latest(crop: str = Query(...)):
    s = _crop_market(crop)
    return {"crop": crop, "data_as_of": s.meta["data_as_of"], "source": s.source, "rows": s.latest_rows(crop)}


@app.get("/api/prices/{crop}/{market}")
def prices(crop: str, market: str, days: int = Query(90, ge=7, le=1095)):
    s = _crop_market(crop, market)
    return {"crop": crop, "market": market, "data_as_of": s.meta["data_as_of"], "source": s.source,
            "latest": s.latest(crop, market), "trend": s.trend(crop, market),
            "history": s.history(crop, market, days), "last_year": s.last_year(crop, market, days)}


@app.get("/api/forecast/overview")
def forecast_overview():
    s = get_store()
    rows = []
    for c in s.catalog["crops"]:
        for r in s.latest_rows(c["id"]):
            fc = s.forecast(c["id"], r["market"]) or {}
            an = s.recent_anomaly(c["id"], r["market"])
            ok = fc.get("available")
            rows.append({"crop": c["id"], "market": r["market"], "date": r["date"], "modal": r["modal"], "change_7d_pct": r["change_7d_pct"],
                         "trend": r["trend"], "arrivals_t": r["arrivals_t"],
                         "point_mean": fc["summary"]["point_mean"] if ok else None, "lo": fc["summary"]["lo"] if ok else None,
                         "hi": fc["summary"]["hi"] if ok else None, "confidence": fc.get("confidence"), "model": fc.get("model"),
                         "anomaly_type": an["type"] if an else None})
    return {"data_as_of": s.meta["data_as_of"], "source": s.source, "rows": rows}


@app.get("/api/forecast/{crop}/{market}")
def forecast(crop: str, market: str):
    s = _crop_market(crop, market)
    fc = s.forecast(crop, market)
    if not fc:
        raise HTTPException(404, "No forecast")
    return {**fc, "source": s.source, "data_as_of": s.meta["data_as_of"]}


class CompareIn(BaseModel):
    crop: str
    quantity_qtl: float = Field(20, gt=0, le=100000)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    transport_rate_per_qtl_km: float | None = Field(None, ge=0, le=100)
    commission_pct: float | None = Field(None, ge=0, le=30)
    handling_per_qtl: float | None = Field(None, ge=0, le=10000)


@app.post("/api/markets/compare")
def markets_compare(body: CompareIn):
    s = _crop_market(body.crop)
    return compare_markets(s, body.crop, body.quantity_qtl, body.lat, body.lon, body.transport_rate_per_qtl_km,
                           body.commission_pct, body.handling_per_qtl)


# ------------------------------------------------------------------ assistant
class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    lang: str = "auto"
    lat: float | None = None
    lon: float | None = None
    quantity_qtl: float | None = Field(None, gt=0, le=100000)


@app.post("/api/assistant/ask")
def assistant_ask(body: AskIn):
    s = get_store()
    origin = (body.lat, body.lon) if body.lat is not None and body.lon is not None else None
    res = ask(body.question, body.lang, s, origin=origin, quantity=body.quantity_qtl)
    res.pop("_facts", None)
    get_db().audit("market_advisor", "answer",
                   f"intent={res['intent']} crop={res['crop']} market={res['market']} lang={res['lang']} llm={res['used_llm']} guard={res['guard']}",
                   actor="farmer")
    return res


class FeedbackIn(BaseModel):
    question: str = Field(..., max_length=500)
    answer: str = Field(..., max_length=3000)
    helpful: bool
    correction: str | None = Field(None, max_length=1000)


@app.post("/api/assistant/feedback")
def assistant_feedback(body: FeedbackIn):
    db = get_db()
    db.execute("INSERT INTO feedback (ts, question, answer, helpful, correction) VALUES (?, ?, ?, ?, ?)",
               (now(), body.question, body.answer, int(body.helpful), body.correction))
    db.audit("market_advisor", "feedback", f"helpful={body.helpful}", actor="farmer")
    return {"ok": True}


@app.get("/api/assistant/feedback")
def assistant_feedback_list(user=Depends(require("officer", "admin"))):
    return {"rows": get_db().query("SELECT * FROM feedback ORDER BY id DESC LIMIT 200")}


_EVAL_CACHE: dict = {}
TEMPLATE_CONSTANTS = {"1", "2", "3", "4", "5", "7", "30"}


def run_eval() -> dict:
    s = get_store()
    key = s.meta["generated_at"]
    if key in _EVAL_CACHE:
        return _EVAL_CACHE[key]
    cases = json.loads((settings.DATA_DIR / "assistant_eval.json").read_text(encoding="utf-8"))
    rows, correct, made_up = [], 0, 0
    for case in cases:
        res = ask(case["question"], case.get("lang", "auto"), s, use_llm=False)
        exp = case["expected"]
        got = {"intent": res["intent"], "crop": res["crop"], "market": res["market"]}
        ok = all(got.get(k) == v for k, v in exp.items())
        allowed = numbers(json.dumps(res["_facts"], ensure_ascii=False, default=str)) | numbers(case["question"]) | TEMPLATE_CONSTANTS
        bad = sorted(numbers(res["answer"]) - allowed)
        made_up += bool(bad)
        correct += ok
        rows.append({"question": case["question"], "lang": case.get("lang", "auto"), "expected": exp, "got": got,
                     "correct": ok, "answer": res["answer"], "unverified_numbers": bad})
    total = len(cases)
    out = {"total": total, "correct": correct, "accuracy": round(correct / total, 3), "target": 0.85,
           "passed": correct / total >= 0.85 and made_up == 0, "made_up_numbers": made_up, "rows": rows}
    _EVAL_CACHE[key] = out
    return out


@app.get("/api/assistant/eval")
def assistant_eval():
    return run_eval()


# ------------------------------------------------------------------ accuracy
@app.get("/api/accuracy")
def accuracy():
    s = get_store()
    acc = dict(s.accuracy)
    ev = run_eval()
    acc["criteria"] = list(acc.get("criteria", [])) + [
        {"key": "assistant", "name_en": "Telugu assistant", "name_te": "తెలుగు సహాయకుడు",
         "target": "At least 85% of test questions answered correctly, with no made-up numbers",
         "value": f"{ev['accuracy']:.0%} ({ev['correct']}/{ev['total']}), {ev['made_up_numbers']} answers with made-up numbers", "passed": ev["passed"]},
        {"key": "ease", "name_en": "Ease of use", "name_te": "వాడుకలో సులభం",
         "target": "At least 8 of 10 test farmers / RSK staff understand the price card without help",
         "value": "Field test pending", "passed": None},
    ]
    return acc


# ------------------------------------------------------------------ alerts
class AlertIn(BaseModel):
    id: str
    crop: str
    market: str
    target: float
    direction: str = "above"


class AlertsIn(BaseModel):
    alerts: list[AlertIn] = Field(default_factory=list, max_length=50)


@app.post("/api/alerts/check")
def alerts_check(body: AlertsIn):
    return {"results": check_targets(get_store(), [a.model_dump() for a in body.alerts])}


@app.get("/api/alerts/feed")
def alerts_feed():
    db = get_db()
    sync_warnings(db, get_store())
    warnings = db.query("SELECT id, crop, market, type, date, en, te, reviewed_at FROM warnings WHERE status = 'approved' ORDER BY date DESC LIMIT 20")
    bulletins = db.query("SELECT id, week_start, title_en, title_te, body_en, body_te, reviewed_at FROM bulletins WHERE status = 'approved' ORDER BY week_start DESC, id DESC LIMIT 5")
    return {"warnings": warnings, "bulletins": bulletins}


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(401, "Wrong username or password")
    get_db().audit("platform", "login", f"{user['username']} ({user['role']})", actor=user["username"])
    return {"token": make_token(user), "user": user}


@app.get("/api/auth/me")
def me(user=Depends(require())):
    return user


# ------------------------------------------------------------------ warnings (officer review)
class ReviewIn(BaseModel):
    decision: str
    note: str | None = Field(None, max_length=500)


@app.get("/api/warnings")
def warnings_list(status: str = "pending", user=Depends(require("officer", "admin"))):
    db = get_db()
    sync_warnings(db, get_store())
    if status == "all":
        rows = db.query("SELECT * FROM warnings ORDER BY date DESC LIMIT 200")
    else:
        rows = db.query("SELECT * FROM warnings WHERE status = ? ORDER BY date DESC LIMIT 200", (status,))
    return {"rows": rows}


@app.post("/api/warnings/{wid}/review")
def warnings_review(wid: str, body: ReviewIn, user=Depends(require("officer", "admin"))):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    db = get_db()
    if not db.query("SELECT id FROM warnings WHERE id = ?", (wid,)):
        raise HTTPException(404, "Warning not found")
    status = "approved" if body.decision == "approve" else "rejected"
    db.execute("UPDATE warnings SET status = ?, reviewed_by = ?, reviewed_at = ?, note = ? WHERE id = ?",
               (status, user["username"], now(), body.note, wid))
    db.audit("alert_agent", "review_warning", f"{wid} -> {status}", actor=user["username"])
    return db.query("SELECT * FROM warnings WHERE id = ?", (wid,))[0]


# ------------------------------------------------------------------ bulletins
class BulletinDraftIn(BaseModel):
    week_start: date | None = None


class BulletinEditIn(BaseModel):
    title_en: str = Field(..., max_length=300)
    title_te: str = Field(..., max_length=300)
    body_en: str = Field(..., max_length=8000)
    body_te: str = Field(..., max_length=8000)


@app.get("/api/bulletins")
def bulletins_list(status: str = "approved", user=Depends(current_user)):
    db = get_db()
    staff = user is not None and user["role"] in ("officer", "admin")
    if not staff or status == "approved":
        rows = db.query("SELECT * FROM bulletins WHERE status = 'approved' ORDER BY week_start DESC, id DESC LIMIT 50")
    elif status == "all":
        rows = db.query("SELECT * FROM bulletins ORDER BY id DESC LIMIT 50")
    else:
        rows = db.query("SELECT * FROM bulletins WHERE status = ? ORDER BY id DESC LIMIT 50", (status,))
    return {"rows": rows}


@app.post("/api/bulletins/draft")
def bulletins_draft(body: BulletinDraftIn | None = None, user=Depends(require("officer", "admin"))):
    b = draft_weekly_bulletin(get_store(), body.week_start if body else None)
    db = get_db()
    bid = db.execute("INSERT INTO bulletins (week_start, status, title_en, title_te, body_en, body_te, created_at, created_by) "
                     "VALUES (?, 'draft', ?, ?, ?, ?, ?, ?) RETURNING id",
                     (b["week_start"], b["title_en"], b["title_te"], b["body_en"], b["body_te"], now(), user["username"]))
    db.audit("alert_agent", "draft_weekly_bulletin", f"bulletin {bid} for week {b['week_start']}", actor=user["username"])
    return db.query("SELECT * FROM bulletins WHERE id = ?", (bid,))[0]


@app.put("/api/bulletins/{bid}")
def bulletins_edit(bid: int, body: BulletinEditIn, user=Depends(require("officer", "admin"))):
    db = get_db()
    rows = db.query("SELECT status FROM bulletins WHERE id = ?", (bid,))
    if not rows:
        raise HTTPException(404, "Bulletin not found")
    db.execute("UPDATE bulletins SET title_en = ?, title_te = ?, body_en = ?, body_te = ?, status = CASE WHEN status = 'approved' THEN 'draft' ELSE status END WHERE id = ?",
               (body.title_en, body.title_te, body.body_en, body.body_te, bid))
    db.audit("alert_agent", "edit_bulletin", f"bulletin {bid} edited", actor=user["username"])
    return db.query("SELECT * FROM bulletins WHERE id = ?", (bid,))[0]


@app.post("/api/bulletins/{bid}/review")
def bulletins_review(bid: int, body: ReviewIn, user=Depends(require("officer", "admin"))):
    if body.decision not in ("approve", "hold"):
        raise HTTPException(400, "decision must be approve or hold")
    db = get_db()
    if not db.query("SELECT id FROM bulletins WHERE id = ?", (bid,)):
        raise HTTPException(404, "Bulletin not found")
    status = "approved" if body.decision == "approve" else "held"
    db.execute("UPDATE bulletins SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?", (status, user["username"], now(), bid))
    db.audit("alert_agent", "review_bulletin", f"bulletin {bid} -> {status}", actor=user["username"])
    return db.query("SELECT * FROM bulletins WHERE id = ?", (bid,))[0]


# ------------------------------------------------------------------ admin
@app.get("/api/admin/quality")
def admin_quality(user=Depends(require("admin"))):
    s = get_store()
    reviews = {r["record_id"]: r for r in get_db().query("SELECT * FROM quality_reviews")}
    q = dict(s.quality)
    q["flagged"] = [{**f, "review": ({"decision": reviews[f["id"]]["decision"], "by": reviews[f["id"]]["reviewed_by"],
                                      "at": reviews[f["id"]]["reviewed_at"]} if f["id"] in reviews else None)} for f in q.get("flagged", [])]
    return q


class QualityReviewIn(BaseModel):
    decision: str


@app.post("/api/admin/quality/{record_id:path}/review")
def admin_quality_review(record_id: str, body: QualityReviewIn, user=Depends(require("admin"))):
    if body.decision not in ("accept", "exclude"):
        raise HTTPException(400, "decision must be accept or exclude")
    if record_id not in {f["id"] for f in get_store().quality.get("flagged", [])}:
        raise HTTPException(404, "Flagged record not found")
    db = get_db()
    db.execute("INSERT INTO quality_reviews (record_id, decision, reviewed_by, reviewed_at) VALUES (?, ?, ?, ?) "
               "ON CONFLICT (record_id) DO UPDATE SET decision = excluded.decision, reviewed_by = excluded.reviewed_by, reviewed_at = excluded.reviewed_at",
               (record_id, body.decision, user["username"], now()))
    db.audit("data_agent", "review_record", f"{record_id} -> {body.decision} (used from the next pipeline run)", actor=user["username"])
    return {"record_id": record_id, "review": {"decision": body.decision, "by": user["username"], "at": now()}}


@app.get("/api/admin/audit")
def admin_audit(limit: int = Query(100, ge=1, le=500), user=Depends(require("admin"))):
    rows = get_db().query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    pipeline = [{"id": f"p{i}", "ts": e["ts"], "agent": e["agent"], "action": e["action"], "detail": e["detail"], "actor": "pipeline"}
                for i, e in enumerate(get_store().meta.get("pipeline_log", []))]
    merged = sorted(rows + pipeline, key=lambda r: r["ts"] or "", reverse=True)[:limit]
    return {"rows": merged}


@app.get("/api/admin/pipeline")
def admin_pipeline(user=Depends(require("admin"))):
    s = get_store()
    hist_path = settings.PROCESSED_DIR / "run_history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    return {"generated_at": s.meta["generated_at"], "data_as_of": s.meta["data_as_of"], "source": s.source,
            "rows": s.meta.get("pipeline_log", []), "history": history[-30:]}
