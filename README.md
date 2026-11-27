# MandiMitra

**AI-powered market intelligence for horticulture farmers** (TechBharat AI CoE, Cohort #2, problem statement C2-17).

MandiMitra ("friend at the market") turns daily mandi data into simple selling advice for **tomato, onion and banana** in
**17 Andhra Pradesh markets** that report these crops to AGMARKNET: today's price, whether the price is likely to rise or
fall in the next 7 days (only where the model has proven it can tell), a **7-day price range**, the **best nearby market
after transport and commission**, and the **reasons**, in **Telugu or English**, by voice or text. It only advises; the
farmer decides.

- **Live app:** https://mandimitra-alpha.vercel.app
- **API docs (OpenAPI):** `/api/docs` on the live app
- **Design document:** C2-17 Solution Design Document v1.0 (13 Oct 2026)

> **Data.** Prices are **real AGMARKNET data** (Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers
> Welfare) from the official data.gov.in API (GODL-India licence): every Andhra Pradesh record for tomato, onion and
> banana since 2022, refreshed twice a day. Weather is real (Open-Meteo). This source has **no arrival quantities**, so
> arrival-based features stay empty until an AGMARKNET export with arrivals is added. See [docs/DATA.md](docs/DATA.md).

**Markets** (chosen from what actually reports, not assumed; the design document said the cluster would be confirmed
on data quality):

| Crop | Markets with their own backtested forecast | Markets with short history (price + low-confidence forecast) |
|---|---|---|
| Tomato | Madanapalle, Kalikiri, Punganur, Palamaner, Valmikipuram (Vayalpad; also answers for Gurramkonda sub-yard), Mulakalacheruvu | Pattikonda, B. Kothakota, V. Kota, Kuppam* |
| Onion | Kurnool | Yerraguntla (price only for now) |
| Banana | Ravulapalem, Ambajipeta | Railway Koduru, Siddavatam, Tiruchanur (Tirupati, price only for now) |

\* Kuppam's official feed has repeated the same price (₹1,212) for every report since 18 Aug 2026, so the app shows it as
"price not changing at the source since 18 Aug" with no forecast, and leaves it out of comparisons. Any market that repeats
one price for 15+ reports in a row is treated this way. Gurramkonda sub-yard's records are copies of Valmikipuram AMC's, so
they are one market in the app.

Anantapur, Kadapa town, Vijayawada and Pulivendula from the design document's example list do not report these crops
in this source, so they are not shown.

**Other crops (farmer's choice, prices only).** Besides the three study crops, a farmer can tap "+ Add a crop" and follow
any of 45 other crops (vegetables, fruits, spices and plantation crops, field crops such as paddy, maize, groundnut,
cotton and pulses). The app then shows the latest official price at every Andhra Pradesh market that reported it in the
last 30 days, with a 30-day chart. These crops get **no forecast**: only the study crops are backtested, and the app says
so. The same daily request fetches all crops for a day, so this adds no extra API load.

## What is built (PoC scope from the design document)

| # | Feature | Where |
|---|---|---|
| M1 | Data pipeline: fetch, name and unit matching, duplicates, sanity rules, data-quality report, admin review of flagged rows | `pipeline/clean.py`, Admin screen |
| M2 | Price board: home screen of small tiles (crop, market, today's price, next-7-days rise/fall, favourite ☆, audio 🔊); tap for today's price by variety, the 7 days ahead and a short chart; source and date on every screen | Home, price detail |
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

**One consistent price per market.** Markets report differently: Madanapalle lists "Local" every day plus a cheaper
"Other" lot on some days, so only Local is followed; Kalikiri reports one price a day whose variety label switches
between "Local" and "Hybrid", so that daily price is followed whatever the label; Ravulapalem reports 6 banana varieties
every day, so its line is their daily median (no arbitrary pick). Today's price for every variety is on the detail page,
and banana markets are not compared on "₹ more" when they report different varieties.

**Forecasting.** For every crop-market pair the pipeline compares three simple baselines (last price, same as last
week, 7-day average), SARIMA(1,1,1)(1,0,1)₇ and LightGBM (one model per crop and horizon, using recent prices,
season, nearby-market prices and weather). Testing is done the honest way: models are trained on older data, the model
choice and range calibration use the next 120 days, and the reported accuracy is measured on the most recent 120 days
that no model has seen. Ranges come from split-conformal calibration of past errors scaled by recent volatility.

**Rise / fall arrows are earned.** An up or down arrow is shown for a market only if that model's past up/down calls
there were right at least 6 times in 10 on recent data (markets with short history are judged on their own record too);
otherwise the app says **"can't say for sure"** and shows the likely range. "No big change" is held to the same rule; on
real tomato and onion data it was rarely right (prices seldom stay within ±3% for a week), so it is not shown. Markets
with less than a year of history use the crop's pooled LightGBM model and are always marked low confidence. The "Why?"
reasons are shown only when LightGBM made the forecast, each with whether it pushes the price up or down.

**Best market** compares only markets within 200 km by road (adjustable), shows each market's variety, and subtracts
transport, commission and handling (all editable).

**Guardrails.** The language model never produces numbers: answers are built from tool output with fixed templates.
If an LLM is configured it may only reword the answer, and the reworded text is used only if every number in it is
found in the tool output (otherwise the template answer is shown). Every answer shows the data date and source; every
agent action is logged; nothing buys, sells or makes payments.

## Current results (backtest on unseen months)

The accuracy report is regenerated on every pipeline run and shown in the app (Dashboard → Accuracy). On **real
AGMARKNET data** as of 27 Nov 2026, test window 30 Jul – 27 Nov 2026, 9 crop-market series with enough history:

| Measure | Target | Result |
|---|---|---|
| Actual prices inside the 80% range | about 80% | **83%** ✓ |
| Rise / fall arrows correct | ≥ 6 in 10 | **60%** of 176 arrows shown ✓ (just at the target; an arrow was shown on 18% of days) |
| Forecast error vs best simple baseline | ≥ 10% lower MAPE | **1.3% lower** (16.8% vs 17.1%) ✗ — LightGBM alone is 4.9% lower |
| Assistant test questions | ≥ 85% correct, no made-up numbers | 50 / 50 on the team's set; 37 / 40 on an independent reviewer's fresh set after fixing what it exposed (32 / 40 before) |
| Daily update reliability | ≥ 95% of days | 24 / 24 tracked days |
| Ease of use (8 of 10 users understand the price card) | field test | pending |

Read these honestly: real tomato prices move a lot within a week (16–23% average error for every model, including "last
price"), so the 10% improvement target is not met; the design document left the targets to be confirmed with the mentor
once data quality was known. The model-selection rule was changed once (27 Nov 2026) after this test window had been
seen, so the 1.3% is optimistic (the earlier rule gave 0.5%); the rule is now frozen and later weeks are a clean test.

**Independent audit (27 Nov 2026).** Four separate reviewers checked the build against the data:
- every price the app shows matched the official records (90 / 90 recent day-records recomputed from the raw file, and
  all 12,390 history rows);
- no feature or model used future prices; two small leaks were found and fixed (a regional average that depended on
  later reports, and calibration days overlapping the test window), which is why the numbers above are lower than first published;
- fixed after the audit: Kuppam's frozen feed, Gurramkonda duplicate, banana variety comparisons, a trend label that
  could say "rising" after 3 falling days, untested "no big change" calls, arrows at short-history markets, reasons and
  warnings shown without evidence or officer review, Telugu wording, and Telugu town names for "where should I sell".

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
  18:00 IST and commits the new `data/processed` files. Vercel redeploys through its Git integration, or through a
  deploy hook if the `VERCEL_DEPLOY_HOOK` secret is set (needed for private repos on the Hobby plan, where commits
  by the Actions bot are not deployed automatically).

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

- Add arrival quantities (AGMARKNET export / teammate's scraper into `data/raw/agmarknet/`) — the strongest missing signal.
- Newer yards (B. Kothakota, V. Kota, Yerraguntla, Railway Koduru, Siddavatam, Tiruchanur) get their own backtest
  once they have a year of history; Kuppam returns when its feed starts changing again.
- Re-measure accuracy on weeks after 27 Nov 2026 with the frozen selection rule (a clean, unseen test).
- Replace transport and commission defaults with the FPO cost survey; road distances are estimated (straight line × 1.3).
- Phone OTP login, WhatsApp / SMS / IVR channels and Bhashini server-side speech are future scope; the PoC uses
  staff logins and the browser's speech engine (Telugu voice depends on the phone).
- Field test with farmers and RSK staff (ease-of-use criterion) is pending.
