# MandiMitra API (v1)

Base path: `/api`. All responses are JSON. Prices are in ₹ per quintal, arrivals in tonnes.
Every data response carries `source` and `data_as_of` so the UI can show date and source on every screen.

`source` object (used everywhere):

```json
{ "code": "AGMARKNET" | "SIMULATED" | "MIXED", "label_en": "AGMARKNET (data.gov.in)", "label_te": "అగ్మార్క్‌నెట్", "is_simulated": false }
```

## Public endpoints

### GET /api/health
`{ "status": "ok", "data_as_of": "2026-11-03", "db": "postgres" | "sqlite" }`

### GET /api/meta
```json
{
  "app": "MandiMitra", "version": "1.0.0",
  "generated_at": "2026-11-04T04:00:00Z",
  "data_as_of": "2026-11-03",
  "source": { ... },
  "is_simulated": true,
  "llm_enabled": false,
  "crops": [ { "id": "tomato", "en": "Tomato", "te": "టమాటా", "shelf_life_days": 4, "markets": ["madanapalle", "kurnool"] } ],
  "markets": [ { "id": "madanapalle", "en": "Madanapalle", "te": "మదనపల్లె", "district": "Annamayya", "lat": 13.55, "lon": 78.5 } ]
}
```

### GET /api/places
Towns/villages a farmer can pick as their pickup point.
`{ "rows": [ { "id": "punganur", "en": "Punganur", "district": "Chittoor", "lat": 13.36, "lon": 78.58 } ] }`

### GET /api/prices/latest?crop=tomato
```json
{ "crop": "tomato", "data_as_of": "2026-11-03", "source": {...},
  "rows": [ { "market": "madanapalle", "date": "2026-11-03", "min": 1300, "max": 2600, "modal": 1900,
              "arrivals_t": 820.5, "change_7d_pct": -8.1, "trend": "rising" | "falling" | "steady", "stale": false } ] }
```

### GET /api/prices/{crop}/{market}?days=90
`days` ∈ 7..1095. Missing (non-reported) days are omitted, never filled.
```json
{ "crop": "tomato", "market": "madanapalle", "data_as_of": "2026-11-03", "source": {...},
  "latest": { "date": "2026-11-03", "min": 1300, "max": 2600, "modal": 1900, "arrivals_t": 820.5 },
  "trend": { "label": "falling", "change_7d_pct": -8.1, "change_30d_pct": 4.2,
             "arrivals_change_7d_pct": 25.3, "down_days_last5": 4, "up_days_last5": 1 },
  "history":   [ { "date": "2026-08-05", "min": 1200, "max": 2400, "modal": 1800, "arrivals_t": 700.0 } ],
  "last_year": [ { "date": "2026-08-05", "modal": 1500 } ]
}
```
`last_year` dates are shifted +1 year so they line up with `history` on one x-axis.

### GET /api/forecast/{crop}/{market}
```json
{ "available": true, "crop": "tomato", "market": "madanapalle", "as_of": "2026-11-03", "last_price": 1900,
  "model": "lightgbm", "model_label": "LightGBM",
  "confidence": "high" | "medium" | "low",
  "confidence_notes": [ { "en": "Prices have been unstable", "te": "..." } ],
  "points": [ { "date": "2026-11-04", "h": 1, "point": 1850, "lo": 1600, "hi": 2050 } ],
  "summary": { "point_mean": 1720, "lo": 1500, "hi": 2000, "direction": "up" | "down" | "flat" },
  "reasons": [ { "key": "arrivals", "en": "Arrivals up 25% from last week", "te": "...", "effect": "up" | "down", "weight": 0.42 } ],
  "advice": { "action": "sell_now" | "wait" | "either", "en": "...", "te": "..." },
  "anomaly": null | { "type": "arrival_flood" | "price_spike" | "price_crash", "date": "2026-11-02", "en": "...", "te": "..." },
  "source": {...}, "data_as_of": "2026-11-03" }
```
When there is too little data: `{ "available": false, "crop": ..., "market": ..., "reason_en": "...", "reason_te": "..." }`.
`points` has 7 rows (h = 1..7, calendar days after `as_of`). The range is an ~80% interval.

### GET /api/forecast/overview
Multi-crop, multi-market table for the FPO / RSK dashboard.
```json
{ "data_as_of": "...", "source": {...},
  "rows": [ { "crop": "tomato", "market": "madanapalle", "date": "2026-11-03", "modal": 1900, "change_7d_pct": -8.1,
              "trend": "falling", "arrivals_t": 820.5, "point_mean": 1720, "lo": 1500, "hi": 2000,
              "confidence": "medium", "model": "lightgbm", "anomaly_type": null | "arrival_flood" } ] }
```

### POST /api/markets/compare
Body:
```json
{ "crop": "tomato", "quantity_qtl": 20, "lat": 13.55, "lon": 78.5,
  "transport_rate_per_qtl_km": 0.75, "commission_pct": 4, "handling_per_qtl": 10 }
```
(the last three are optional; defaults are returned in `assumptions`)
```json
{ "crop": "tomato", "quantity_qtl": 20, "origin": { "lat": 13.55, "lon": 78.5 },
  "assumptions": { "transport_rate_per_qtl_km": 0.75, "commission_pct": 4, "handling_per_qtl": 10, "road_factor": 1.3 },
  "rows": [ { "rank": 1, "market": "tirupati", "date": "2026-11-03", "modal": 2000, "distance_km": 120.4,
              "transport": 90, "commission": 80, "handling": 10, "net_per_qtl": 1820, "net_total": 36400,
              "badges": ["best", "highest_price", "nearest"], "flags": ["arrival_flood", "stale"],
              "forecast": { "point_mean": 1720, "lo": 1500, "hi": 2000, "confidence": "medium" } } ],
  "best_vs_nearest": { "best": "tirupati", "nearest": "madanapalle", "extra_per_qtl": 46, "extra_total": 920 },
  "source": {...}, "data_as_of": "..." }
```

### POST /api/assistant/ask
Body: `{ "question": "Madanapalle lo tomato rate entha?", "lang": "te" | "en" | "auto" }`
```json
{ "answer": "...", "lang": "te", "intent": "price" | "trend" | "forecast" | "best_market" | "sell_or_wait" | "arrivals" | "help" | "unknown",
  "crop": "tomato" | null, "market": "madanapalle" | null,
  "data_date": "2026-11-03", "source_label": "...", "used_llm": false, "guard": "passed" | "fallback" | "n/a",
  "suggestions": ["Kurnool lo ullipaya dhara entha?"] }
```

### POST /api/assistant/feedback
`{ "question": "...", "answer": "...", "helpful": false, "correction": "optional text" }` → `{ "ok": true }`

### GET /api/assistant/eval
Result of running the 50-question Telugu/English test set through the assistant.
```json
{ "total": 50, "correct": 46, "accuracy": 0.92, "target": 0.85, "passed": true, "made_up_numbers": 0,
  "rows": [ { "question": "...", "lang": "te", "expected": {"intent": "price", "crop": "tomato", "market": "madanapalle"},
              "got": {...}, "correct": true } ] }
```

### POST /api/alerts/check
Body: `{ "alerts": [ { "id": "a1", "crop": "onion", "market": "kurnool", "target": 2400, "direction": "above" | "below" } ] }`
→ `{ "results": [ { "id": "a1", "triggered": true, "current": 2450, "date": "2026-11-03" } ] }`

### GET /api/alerts/feed
Only items approved by an extension officer.
```json
{ "warnings":  [ { "id": "w-tomato-kurnool-2026-11-02-arrival_flood", "crop": "tomato", "market": "kurnool", "type": "arrival_flood",
                   "date": "2026-11-02", "en": "...", "te": "...", "reviewed_at": "..." } ],
  "bulletins": [ { "id": 3, "week_start": "2026-11-02", "title_en": "...", "title_te": "...", "body_en": "...", "body_te": "...", "reviewed_at": "..." } ] }
```

### GET /api/accuracy
Backtest report on unseen recent months.
```json
{ "generated_at": "...", "test_window": { "start": "...", "end": "...", "days": 120 },
  "calibration_window": { "start": "...", "end": "...", "days": 120 },
  "model_labels": { "naive": "Last price", "seasonal_naive": "Same as last week", "moving_average": "7-day average", "sarima": "SARIMA", "lightgbm": "LightGBM" },
  "overall": { "mape": { "naive": 9.1, "seasonal_naive": 10.2, "moving_average": 9.8, "sarima": 8.9, "lightgbm": 7.6, "selected": 7.5 },
               "best_baseline": "naive", "improvement_pct": 17.6, "coverage": 0.81, "direction_accuracy": 0.64 },
  "criteria": [ { "key": "accuracy", "name_en": "...", "name_te": "...", "target": "...", "value": "...", "passed": true } ],
  "by_horizon": [ { "h": 1, "mape": { "naive": 4.0, "lightgbm": 3.6 } } ],
  "series": [ { "crop": "tomato", "market": "madanapalle", "n_test": 110, "mape": { "naive": 9.0, "lightgbm": 7.0 },
                "selected": "lightgbm", "coverage": 0.8, "direction_accuracy": 0.66, "improvement_pct": 22.2 } ] }
```

## Staff endpoints (Authorization: Bearer <token>)

Roles: `admin`, `officer` (extension / RSK), `fpo`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | /api/auth/login | – | `{username, password}` → `{token, user: {username, role, name}}` |
| GET | /api/auth/me | any | current user |
| GET | /api/warnings?status=pending\|approved\|rejected\|all | officer, admin | big-move warnings drafted by the Alert Agent |
| POST | /api/warnings/{id}/review | officer, admin | `{decision: "approve"\|"reject", note?}` |
| GET | /api/bulletins?status=draft\|approved\|held\|all | public sees approved only | weekly bulletins |
| POST | /api/bulletins/draft | officer, admin | `{week_start?}` → draft bulletin (Telugu + English) |
| PUT | /api/bulletins/{id} | officer, admin | edit `{title_en, title_te, body_en, body_te}` |
| POST | /api/bulletins/{id}/review | officer, admin | `{decision: "approve"\|"hold"}` |
| GET | /api/admin/quality | admin | data-quality report + flagged records with review status |
| POST | /api/admin/quality/{record_id}/review | admin | `{decision: "accept"\|"exclude"}` |
| GET | /api/admin/audit?limit=100 | admin | log of every agent action |
| GET | /api/admin/pipeline | admin | last pipeline run log |
| GET | /api/assistant/feedback | officer, admin | farmer feedback / corrections on answers |

Warning row: `{ id, crop, market, type, date, magnitude, en, te, status, reviewed_by, reviewed_at, note }`.
Bulletin row: `{ id, week_start, status, title_en, title_te, body_en, body_te, created_at, created_by, reviewed_by, reviewed_at }`.
Quality: `{ generated_at, source, rows_raw, rows_clean, duplicates_removed, name_fixes, unit_fixes, checks: [{name, passed, detail}],
series: [{crop, market, first_date, last_date, days_reported, missing_days, missing_pct, flagged, stale}],
flagged: [{id, crop, market, date, rule, detail, min, max, modal, review: null | {decision, by, at}}] }`.
Audit row: `{ id, ts, agent, action, detail, actor }`.

Errors: `{ "detail": "message" }` with 4xx status.
