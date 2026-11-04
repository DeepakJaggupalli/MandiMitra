# MandiMitra

**AI-powered market intelligence for horticulture farmers** (TechBharat AI CoE, Cohort #2, problem statement C2-17).

MandiMitra ("friend at the market") turns daily mandi data into simple selling advice for **tomato, onion and banana** in
eight Andhra Pradesh markets (Madanapalle, Pattikonda, Kurnool, Anantapur, Kadapa, Vijayawada, Tirupati, Pulivendula):
today's price, the trend, a **7-day price range**, the **best market after transport and commission**, and the
**reasons** behind each result, in **Telugu or English**, by voice or text. It only advises; the farmer decides.

- **Live app:** _added after deployment_
- **API docs (OpenAPI):** `/api/docs` on the live app
- **Design document:** C2-17 Solution Design Document v1.0 (13 Oct 2026)

> **Data note.** Until the real AGMARKNET history is added (see [docs/DATA.md](docs/DATA.md)), the app runs on a
> **simulated dataset in AGMARKNET format**. It is clearly marked "Sample data" in the app and in every API response
> (`source.is_simulated`). Weather is real (Open-Meteo). Adding a real export to `data/raw/agmarknet/` switches
> everything (models, backtest, accuracy report) to real data on the next pipeline run.

## What is built (PoC scope from the design document)

| # | Feature | Where |
|---|---|---|
| M1 | Data pipeline: fetch, name and unit matching, duplicates, sanity rules, data-quality report, admin review of flagged rows | `pipeline/clean.py`, Admin screen |
| M2 | Price and trend board: min / modal / max, arrivals, 7 / 30 / 90-day and 1-year charts, same period last year, source and date on every screen | Prices tab |
| M3 | 7-day price range forecast: most likely price, ~80% range, high / medium / low confidence | `pipeline/forecast.py`, Prices tab |
| M4 | Market comparison by money in hand after transport, commission and handling (editable), for the farmer's quantity and pickup point | Markets tab, `backend/app/netprice.py` |
| M5 | Top three reasons for every forecast in plain Telugu / English (LightGBM TreeSHAP) | `pipeline/explain.py` |
| M6 | Accuracy report: backtest on unseen recent months against simple baselines, success criteria | Dashboard → Accuracy |
| S1 | Telugu voice and chat assistant through read-only tools, tested on 50 questions, no made-up numbers | Ask tab, `backend/app/assistant.py` |
| S2 | Target-price alerts and big-move warnings inside the app | Alerts tab |
| S3 | FPO / extension dashboard: multi-crop view, collective-sale planner, weekly Telugu bulletin with approval step | Dashboard |
| S4 | Weather signal (rainfall, temperature) in the model | `pipeline/sources/weather.py` |
| S5 | Offline-friendly PWA: last loaded prices visible without internet | service worker (`vite-plugin-pwa`) |

## How it works

```
Users ─ Farmer app (PWA, Telugu first) · Voice/chat · FPO/RSK dashboard · Admin console
          │  React + TypeScript, Recharts, Leaflet
Backend ─ FastAPI (Vercel Python function): prices, trends, forecasts, net-price comparison,
          assistant, alerts, bulletins, login + roles, audit log
          │
Agents ── Data Agent → Forecast Agent → Alert Agent      (daily, GitHub Actions)
          Market Advisor (on every question, read-only tools)
          │
Data ──── data/processed/*.json (pipeline output) · Postgres/SQLite (reviews, bulletins, audit)
          │
External ─ AGMARKNET (export / data.gov.in API) · Open-Meteo weather · OpenStreetMap tiles
```

**Agents and their tools** (each agent can use only its own tools; farmer-facing tools are read-only):

| Agent | Trigger | Tools | Human role |
|---|---|---|---|
| Data Agent | daily schedule + manual run | `fetch_agmarknet`, `fetch_weather`, `match_names`, `convert_units`, `check_quality`, `save_data` | admin accepts / excludes flagged rows |
| Forecast Agent | after each data update | `build_features`, `run_baselines`, `run_models`, `make_range`, `explain_forecast`, `detect_unusual` | expert reviews accuracy before model changes |
| Market Advisor | a farmer's question | `get_price`, `get_trend`, `get_forecast`, `compare_markets`, browser speech-to-text / text-to-speech | farmer decides; staff see feedback and corrections |
| Alert Agent | after each forecast | `check_targets`, `detect_unusual`, `draft_alert`, `draft_weekly_bulletin` | officer approves warnings and bulletins before farmers see them |

**Forecasting.** For every crop-market pair the pipeline compares three simple baselines (last price, same as last
week, 7-day average), SARIMA(1,1,1)(1,0,1)₇ and LightGBM (one model per crop and horizon, using recent prices,
arrivals, season, nearby-market prices and weather). Testing is done the honest way: models are trained on older data,
the model choice and range calibration use the next 120 days, and the reported accuracy is measured on the most recent
120 days that no model has seen. Ranges come from split-conformal calibration of past errors scaled by recent
volatility, so they widen when prices are unstable. Confidence drops when the range is wide, data is stale or missing,
or an unusual movement was detected.

**Guardrails.** The language model never produces numbers: answers are built from tool output with fixed templates.
If an LLM is configured it may only reword the answer, and the reworded text is used only if every number in it is
found in the tool output (otherwise the template answer is shown). Every answer shows the data date and source; every
agent action is logged; nothing buys, sells or makes payments.

## Current results (backtest on unseen months)

The accuracy report is regenerated on every pipeline run and shown in the app (Dashboard → Accuracy). On the current
(simulated) dataset:

| Measure | Target | Result |
|---|---|---|
| Forecast error vs best simple baseline | ≥ 10% lower MAPE | _filled from latest run_ |
| Actual prices inside the 80% range | about 80% | _filled from latest run_ |
| Direction of movement | ≥ 6 in 10 | _filled from latest run_ |
| Assistant test questions | ≥ 85% correct, no made-up numbers | _filled from latest run_ |

These numbers prove the pipeline end to end; they must be re-measured on real AGMARKNET data before any claim.

## Running locally

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pipeline.run                                # builds data/processed (≈1–2 min)
uvicorn backend.app.main:app --port 8000              # API on http://127.0.0.1:8000/api/docs

cd frontend && npm ci && npm run dev                  # app on http://localhost:5173 (proxies /api)
python -m pytest tests -q                             # tests
```

Demo staff accounts (change them with `STAFF_USERS` in production): `officer / officer@123`,
`admin / admin@123`, `fpo / fpo@123`. Farmers do not need an account.

## Deployment

- **Vercel** serves the built PWA (`frontend/dist`) and the FastAPI app as one Python function (`api/index.py`,
  rewrites in `vercel.json`).
- **GitHub Actions**: `ci.yml` runs tests and the frontend build; `daily-pipeline.yml` runs the agents at 09:30 and
  18:00 IST, commits the new `data/processed` files, and Vercel redeploys.

Environment variables (all optional except `JWT_SECRET` in production):

| Variable | Used by | Purpose |
|---|---|---|
| `JWT_SECRET` | API | signing key for staff logins |
| `DATABASE_URL` / `POSTGRES_URL` | API, pipeline | Postgres for reviews, bulletins, warnings, audit log (SQLite fallback) |
| `STAFF_USERS` | API | JSON list of `{username, password, role, name}` |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | API | any OpenAI-compatible endpoint (e.g. Sarvam, Groq) for rewording answers |
| `DATA_GOV_IN_API_KEY` | pipeline (GitHub secret) | official AGMARKNET prices from data.gov.in |

## Project layout

```
api/index.py              Vercel entry point
backend/app/              FastAPI app: store, assistant (Market Advisor), alert agent, net price, auth, db
pipeline/                 Data Agent + Forecast Agent (sources/, clean, features, forecast, explain, anomalies, run)
data/catalog.json         crops, markets, aliases, crop calendar, pickup points, cost defaults
data/processed/           pipeline output served by the API
data/assistant_eval.json  50 test questions with expected answers
frontend/                 React + TypeScript PWA
tests/                    pytest suite
docs/                     API contract, data guide
```

## Limits and next steps

- Replace the simulated prices with the AGMARKNET history (3+ years, 3 crops, 8 markets) and re-run the backtest.
- Replace transport and commission defaults with the FPO cost survey; road distances are estimated (straight line × 1.3).
- Phone OTP login, WhatsApp / SMS / IVR channels and Bhashini server-side speech are future scope; the PoC uses
  staff logins and the browser's speech engine (Telugu voice depends on the phone).
- Field test with farmers and RSK staff (ease-of-use criterion) is pending.
