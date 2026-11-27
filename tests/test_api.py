import warnings
from urllib.parse import quote

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from backend.app.store import get_store  # noqa: E402

client = TestClient(app)
S = get_store()
SERIES = sorted(k.split("|") for k in S.prices)  # [crop, market] pairs that have data
FC = [k.split("|") for k, v in S.forecasts.items() if v.get("available")]


def login(user):
    r = client.post("/api/auth/login", json={"username": user, "password": f"{user}@123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_meta():
    assert client.get("/api/health").json()["status"] == "ok"
    m = client.get("/api/meta").json()
    assert {c["id"] for c in m["crops"]} == {"tomato", "onion", "banana"}
    assert len(m["markets"]) == len(S.catalog["markets"]) >= 3
    assert m["source"]["code"] in ("AGMARKNET", "SIMULATED", "MIXED")
    assert m["is_simulated"] == (m["source"]["code"] == "SIMULATED")
    assert SERIES, "no price series at all"


def test_prices_latest_and_history():
    for crop in {c for c, _ in SERIES}:
        r = client.get("/api/prices/latest", params={"crop": crop}).json()
        assert r["rows"]
        for row in r["rows"]:
            assert row["min"] <= row["modal"] <= row["max"]
            assert row["trend"] in ("rising", "falling", "steady", "mixed")
    crop, market = SERIES[0]
    h = client.get(f"/api/prices/{crop}/{market}", params={"days": 30}).json()
    assert h["latest"]["date"] <= h["data_as_of"]
    assert len(h["history"]) <= 30
    dates = [x["date"] for x in h["history"]]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    assert all(x["modal"] is not None for x in h["history"])  # missing days are omitted, not filled
    assert isinstance(h["varieties_today"], list)


def test_unknown_crop_market():
    assert client.get("/api/prices/latest", params={"crop": "mango"}).status_code == 404
    assert client.get("/api/forecast/tomato/atlantis").status_code == 404


def test_forecast_shape():
    assert FC, "no crop-market pair has a forecast"
    crop, market = FC[0]
    f = client.get(f"/api/forecast/{crop}/{market}").json()
    assert f["available"] is True
    assert len(f["points"]) == 7 and [p["h"] for p in f["points"]] == list(range(1, 8))
    for p in f["points"]:
        assert p["lo"] <= p["point"] <= p["hi"]
    assert f["confidence"] in ("high", "medium", "low")
    assert len(f["reasons"]) <= 3 and all(r["te"] and r["en"] for r in f["reasons"])
    assert f["advice"]["action"] in ("sell_now", "wait", "either")
    assert f["summary"]["direction"] in ("up", "down", "flat", "unclear")
    ov = client.get("/api/forecast/overview").json()
    assert len(ov["rows"]) == len(SERIES)
    assert all(r["direction"] in ("up", "down", "flat", "unclear", None) for r in ov["rows"])


def test_compare_net_price():
    crop = SERIES[0][0]
    mk = S.markets[SERIES[0][1]]
    r = client.post("/api/markets/compare", json={"crop": crop, "quantity_qtl": 20, "lat": mk["lat"], "lon": mk["lon"]}).json()
    nets = [x["net_per_qtl"] for x in r["rows"]]
    assert nets == sorted(nets, reverse=True)
    for x in r["rows"]:
        assert x["net_per_qtl"] == x["modal"] - x["transport"] - x["commission"] - x["handling"]
        assert x["net_total"] == round(x["net_per_qtl"] * 20)
    assert "best" in r["rows"][0]["badges"]
    b = r["best_vs_nearest"]
    if b is None:  # banana: different varieties are not compared on gain
        assert r["varieties_differ"] is True
    else:
        assert b["extra_total"] == round(b["extra_per_qtl"] * 20)
    assert all(not S.stale(x["date"]) for x in r["rows"])  # old / frozen prices are not a basis for a trip
    custom = client.post("/api/markets/compare", json={"crop": crop, "quantity_qtl": 20, "lat": mk["lat"], "lon": mk["lon"],
                                                         "transport_rate_per_qtl_km": 0, "commission_pct": 0, "handling_per_qtl": 0}).json()
    assert all(x["net_per_qtl"] == x["modal"] for x in custom["rows"])


def test_assistant_answers_and_eval():
    crop, market = SERIES[0]
    q = f"{S.markets[market]['en']} lo {S.crops[crop]['en'].lower()} rate entha?"
    r = client.post("/api/assistant/ask", json={"question": q, "lang": "te"}).json()
    assert r["intent"] == "price" and r["crop"] == crop and r["market"] == market
    assert "₹" in r["answer"] and r["data_date"]
    e = client.post("/api/assistant/ask", json={"question": f"Where should I sell 10 tonnes of {S.crops[crop]['en'].lower()}?", "lang": "en"}).json()
    assert e["intent"] == "best_market" and "100 quintals" in e["answer"]
    ev = client.get("/api/assistant/eval").json()
    assert ev["total"] >= 50 and ev["accuracy"] >= 0.85 and ev["made_up_numbers"] == 0


def test_alert_check():
    crop, market = SERIES[0]
    last = S.latest(crop, market)["modal"]
    r = client.post("/api/alerts/check", json={"alerts": [
        {"id": "a", "crop": crop, "market": market, "target": last - 1, "direction": "above"},
        {"id": "b", "crop": crop, "market": market, "target": last - 1, "direction": "below"}]}).json()
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
    crop, market = SERIES[0]
    fake = {"id": "w-test", "crop": crop, "market": market, "type": "price_spike", "date": S.meta["data_as_of"],
            "magnitude": 24.0, "en": "Price spike test", "te": "పరీక్ష", "recent": True}
    S.anomalies.setdefault("recent", []).append(fake)
    try:
        h = login("officer")
        assert any(w["id"] == "w-test" for w in client.get("/api/warnings", headers=h).json()["rows"])
        assert client.post("/api/warnings/w-test/review", json={"decision": "approve"}, headers=h).json()["status"] == "approved"
        assert any(w["id"] == "w-test" for w in client.get("/api/alerts/feed").json()["warnings"])
    finally:
        S.anomalies["recent"].remove(fake)


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
    assert 0.0 <= a["overall"]["coverage"] <= 1.0
    assert a["series"] and all("production_model" in s for s in a["series"])
