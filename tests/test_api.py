import warnings
from urllib.parse import quote

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from backend.app.store import get_store  # noqa: E402

client = TestClient(app)


def login(user):
    r = client.post("/api/auth/login", json={"username": user, "password": f"{user}@123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_meta():
    assert client.get("/api/health").json()["status"] == "ok"
    m = client.get("/api/meta").json()
    assert {c["id"] for c in m["crops"]} == {"tomato", "onion", "banana"}
    assert len(m["markets"]) == 8
    assert m["source"]["code"] in ("AGMARKNET", "SIMULATED", "MIXED")


def test_prices_latest_and_history():
    r = client.get("/api/prices/latest", params={"crop": "tomato"}).json()
    assert len(r["rows"]) >= 6
    for row in r["rows"]:
        assert row["min"] <= row["modal"] <= row["max"]
        assert row["trend"] in ("rising", "falling", "steady")
    h = client.get("/api/prices/tomato/madanapalle", params={"days": 30}).json()
    assert h["latest"]["date"] <= h["data_as_of"]
    assert 0 < len(h["history"]) <= 30
    dates = [x["date"] for x in h["history"]]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    assert all(x["modal"] is not None for x in h["history"])  # missing days are omitted, not filled


def test_unknown_crop_market():
    assert client.get("/api/prices/latest", params={"crop": "mango"}).status_code == 404
    assert client.get("/api/forecast/banana/pattikonda").status_code == 404


def test_forecast_shape():
    f = client.get("/api/forecast/onion/kurnool").json()
    assert f["available"] is True
    assert len(f["points"]) == 7 and [p["h"] for p in f["points"]] == list(range(1, 8))
    for p in f["points"]:
        assert p["lo"] <= p["point"] <= p["hi"]
    assert f["confidence"] in ("high", "medium", "low")
    assert 1 <= len(f["reasons"]) <= 3 and all(r["te"] and r["en"] for r in f["reasons"])
    assert f["advice"]["action"] in ("sell_now", "wait", "either")
    ov = client.get("/api/forecast/overview").json()
    assert len(ov["rows"]) == 19


def test_compare_net_price():
    r = client.post("/api/markets/compare", json={"crop": "tomato", "quantity_qtl": 20, "lat": 13.55, "lon": 78.50}).json()
    nets = [x["net_per_qtl"] for x in r["rows"]]
    assert nets == sorted(nets, reverse=True)
    for x in r["rows"]:
        assert x["net_per_qtl"] == x["modal"] - x["transport"] - x["commission"] - x["handling"]
        assert x["net_total"] == round(x["net_per_qtl"] * 20)
    assert "best" in r["rows"][0]["badges"]
    b = r["best_vs_nearest"]
    assert b["extra_total"] == round(b["extra_per_qtl"] * 20)
    custom = client.post("/api/markets/compare", json={"crop": "tomato", "quantity_qtl": 20, "lat": 13.55, "lon": 78.5,
                                                         "transport_rate_per_qtl_km": 0, "commission_pct": 0, "handling_per_qtl": 0}).json()
    assert all(x["net_per_qtl"] == x["modal"] for x in custom["rows"])


def test_assistant_answers_and_eval():
    r = client.post("/api/assistant/ask", json={"question": "Madanapalle lo tomato rate entha?", "lang": "te"}).json()
    assert r["intent"] == "price" and r["crop"] == "tomato" and r["market"] == "madanapalle"
    assert "₹" in r["answer"] and r["data_date"]
    e = client.post("/api/assistant/ask", json={"question": "Where should I sell 10 tonnes of onion?", "lang": "en"}).json()
    assert e["intent"] == "best_market" and "100 quintals" in e["answer"]
    ev = client.get("/api/assistant/eval").json()
    assert ev["total"] == 50 and ev["accuracy"] >= 0.85 and ev["made_up_numbers"] == 0


def test_alert_check():
    last = get_store().latest("onion", "kurnool")["modal"]
    r = client.post("/api/alerts/check", json={"alerts": [
        {"id": "a", "crop": "onion", "market": "kurnool", "target": last - 1, "direction": "above"},
        {"id": "b", "crop": "onion", "market": "kurnool", "target": last - 1, "direction": "below"}]}).json()
    assert {x["id"]: x["triggered"] for x in r["results"]} == {"a": True, "b": False}


def test_auth_and_roles():
    assert client.post("/api/auth/login", json={"username": "officer", "password": "nope"}).status_code == 401
    assert client.get("/api/warnings").status_code == 401
    assert client.get("/api/admin/quality", headers=login("officer")).status_code == 403
    assert client.get("/api/admin/quality", headers=login("admin")).status_code == 200


def test_bulletin_approval_flow():
    h = login("officer")
    b = client.post("/api/bulletins/draft", json={}, headers=h).json()
    assert b["status"] == "draft" and "₹" in b["body_en"] and b["body_te"]
    assert all(x["id"] != b["id"] for x in client.get("/api/alerts/feed").json()["bulletins"])  # drafts are not public
    edit = {k: b[k] for k in ("title_en", "title_te", "body_te")}
    edit["body_en"] = b["body_en"] + "\n\nEdited."
    assert client.put(f"/api/bulletins/{b['id']}", headers=h, json=edit).json()["body_en"].endswith("Edited.")
    a = client.post(f"/api/bulletins/{b['id']}/review", json={"decision": "approve"}, headers=h).json()
    assert a["status"] == "approved" and a["reviewed_by"] == "officer"
    assert any(x["id"] == b["id"] for x in client.get("/api/alerts/feed").json()["bulletins"])


def test_warning_review_flow():
    s = get_store()
    fake = {"id": "w-test", "crop": "tomato", "market": "kurnool", "type": "arrival_flood", "date": s.meta["data_as_of"],
            "magnitude": 2.4, "en": "Arrival flood test", "te": "పరీక్ష", "recent": True}
    s.anomalies.setdefault("recent", []).append(fake)
    try:
        h = login("officer")
        assert any(w["id"] == "w-test" for w in client.get("/api/warnings", headers=h).json()["rows"])
        assert client.post("/api/warnings/w-test/review", json={"decision": "approve"}, headers=h).json()["status"] == "approved"
        assert any(w["id"] == "w-test" for w in client.get("/api/alerts/feed").json()["warnings"])
    finally:
        s.anomalies["recent"].remove(fake)


def test_quality_review_and_audit():
    h = login("admin")
    q = client.get("/api/admin/quality", headers=h).json()
    assert q["rows_clean"] > 0 and isinstance(q["checks"], list)
    if q["flagged"]:
        rid = q["flagged"][0]["id"]
        r = client.post(f"/api/admin/quality/{quote(rid, safe='')}/review", json={"decision": "exclude"}, headers=h)
        assert r.status_code == 200
    audit = client.get("/api/admin/audit", headers=h).json()["rows"]
    assert any(a["agent"] == "data_agent" for a in audit)
    assert client.get("/api/admin/pipeline", headers=h).json()["rows"]


def test_accuracy_report():
    a = client.get("/api/accuracy").json()
    keys = {c["key"] for c in a["criteria"]}
    assert {"accuracy", "coverage", "direction", "assistant", "ease"} <= keys
    assert 0.6 <= a["overall"]["coverage"] <= 0.95
