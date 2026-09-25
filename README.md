# SatQuery AI

<img src="frontend/public/logo.png" alt="SatQuery AI — from satellites to solutions" width="440" />

**AI-powered natural-language satellite data query system** — ask questions in
plain English about the Earth, and get agent-driven geospatial analyses with
maps, charts, verification and downloadable reports.

Supports **Optical · SAR · DEM · Vector · Time-Series · Tabular** data, a fully
labeled **demo catalog** (so core workflows run instantly with no keys), and a
**real-time data layer** that streams genuine live observations from key-free
public APIs — no account required.

---

## ✨ Features

| Area | What you get |
|---|---|
| **Querying** | Natural-language box + example queries, live query-understanding panel (location / date / phenomenon / data type / analysis / agent) |
| **Real-time data** | Live USGS earthquakes + Open-Meteo weather/climate (genuine observations, 2-min cache, auto-refresh) — cards open full detail modals with actual values |
| **Agentic AI** | SAR Agent, Optical Agent, Temporal Agent, Fusion Agent — auto-selected per query (LangGraph optional, native orchestrator otherwise) |
| **Processing** | Flood mapping, change detection, classification, object detection, time-series analysis, terrain (DEM), scene search, multi-source fusion |
| **Mapping** | Interactive Leaflet map: dark/satellite/street baselines, layers, severity/class colouring, AOI bounds, live legend, charts |
| **Execution trace** | Every analysis persists an explicit `[EXECUTION TRACE]` — target task, sensor **modality** (Sentinel-1 SAR / Sentinel-2 MSI / SAR+Optical fusion / live API), chained tool list, per-step results and uncertainty notes — rendered as a stepper on the result page and inside every PDF/DOCX/MD/HTML export |
| **Spectral indices** | NDVI / NDWI / NDBI band-ratio engine (physically-grounded simulated reflectance), with SAR backscatter σ⁰ signature analysis and cross-modal verification checks |
| **GeoTools** | Pure-Python **GeoTIFF** header parser (EPSG/CRS, pixel-scale, tiepoint, bounds), WKT + GeoJSON footprints, spectral-index explorer and a synthetic demo raster for offline exploration |
| **Change Analysis** | Historical **Date 1 vs Date 2** location change: place-name/GPS geocoding (gazetteer + Nominatim), imagery inventory (STAC Earth Search metadata or deterministic demo scenes), NDVI/NDBI/NDWI + Change-Vector differencing, hotspot clustering, signed change heatmap, before/after compare slider, **GeoTIFF/GeoJSON/Markdown** exports, and a query-aware AI/VLM report |
| **Details** | Every dataset / live-event / saved card is clickable → full modal with map preview, fact tiles, metadata, series chart |
| **Reports** | GeoJSON, CSV, Markdown, HTML, **PDF (server-side reportlab + in-browser jsPDF)** and **DOCX** exports |
| **Google Docs** | **"Publish to Google Docs"** creates a real Google Document via OAuth when credentials are configured — otherwise the app offers a Google-Docs-compatible `.docx` that opens straight in Google Docs / Word (feature never breaks) |
| **Auth** | Role-based registration (Student / Researcher / GIS Analyst / Organization), 6-digit OTP e-mail verification, JWT access + refresh with persisted session hashes, TOTP two-factor (enforced for Government/Defense orgs), active sessions & devices, password change with OTP re-verification, configurable inactivity auto-logout with heartbeat, WebSocket session-revocation broadcasts |
| **Data** | 11 seeded demo datasets + 2 live real-time feeds (earthquakes, weather), always honestly labelled |
| **Admin** | Health & stats endpoints, user management, demo re-seeding, logging, rate limiting, role-based access |
| **UX** | Fully responsive dark/light space-inspired UI, glassy cards, gradient accents, mobile sidebar, skeletons, empty states, error handling |

> **Trust, honestly:** demo results are **clearly labeled simulated**. The real-time
> section shows **actual USGS / Open-Meteo observations** with their source and
> observed-at timestamps. The API never presents simulated data as real.
## 🚀 Quick start (5 minutes)

```bash
# Backend (Python 3.11+ recommended)
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt

cp .env.example .env             # optional; defaults work out of the box

# Frontend
cd ../frontend
npm install
```

### Run — one command (recommended)

```bash
# From the project root — starts the backend API AND the frontend together.
# (First run installs any missing frontend dependencies automatically.)
python run.py

# -> Frontend app : http://localhost:5173
# -> Backend API  : http://localhost:8000   (Swagger at /docs)
# Press Ctrl+C to stop both.
```

Useful flags: `--backend-only` (API only), `--reload` (auto-restart the backend
on code changes), `--port 8001` / `--frontend-port 5174` (different ports).

### Run — two terminals (classic dev mode)

```bash
# Terminal 1 — Backend API
cd backend
.venv\Scripts\python run.py       # or: uvicorn app.main:app --reload
# -> http://localhost:8000  (Swagger docs at /docs)

# Terminal 2 — Frontend
cd frontend
npm run dev
# -> http://localhost:5173
```

Demo accounts (seeded automatically):

| Role | Email | Password |
|---|---|---|
| Admin | `admin@satquery.ai` | `Admin@123` |
| Analyst | `demo@satquery.ai` | `Demo@123` |

Or register your own account in the UI.

> **No MongoDB? No problem.** The backend runs against a thread-safe local
> JSON store (`backend/data/local_db.json`) when MongoDB is unreachable
> (`DB_MODE=auto`). To force MongoDB, see config below.
## 🎨 Branding & logo

The brand is **SatQuery AI** (artwork: *“from satellites to solutions”*). Both
brand files are transparent PNGs: the square mark sits directly on the dark app
shell, while the lockup keeps a light plate because its wordmark is deep navy.

To swap the logo, replace these two files, then copy the new lockup into the API
(the backend cannot read the frontend bundle):

```bash
cp frontend/public/logo.png backend/app/assets/logo.png
```

| Asset | Used by |
|---|---|
| `frontend/public/logo.png` — lockup (mark + wordmark + tagline), 1400×467 | README header, in-app sidebar / auth screens / 404 (`Logo.jsx`), `og:image`, client-side PDF export |
| `frontend/public/logo-mark.png` — square orbit mark, 256×256 | favicon, apple-touch-icon, collapsed sidebar |
| `backend/app/assets/logo.png` — copy of the lockup | HTML + PDF report exports (inlined, so exports stay self-contained) |
| `frontend/src/components/Logo.jsx` | one component used by the sidebar, auth screens and the 404 page |
| e-mail templates | text-only brand (`SMTP_FROM_NAME`, default `SatQuery AI`) — intentionally no embedded image, for reliable delivery |

Reports embed the logo as a base64 data URI / inline image, so the exported files
stay self-contained; if the artwork is missing the exports fall back to a
text-only brand instead of failing.

**Render size matters.** In the artwork the wordmark is only ~35% of the image
height and the tagline ~7%, so a small render leaves the words unreadable. The
lockup therefore needs ≥60px on screen (the sidebar renders it at 66px, auth
screens at 78px) and ≥15mm in PDFs; 24mm also resolves the tagline. `Logo.jsx`
enforces the 60px floor — keep new placements at or above it.

## 📦 Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, CORS, WS endpoint, lifespan
│   │   ├── config.py             # env-driven settings
│   │   ├── storage.py            # MongoDB ⇄ local-JSON dual backend
│   │   ├── security.py           # PBKDF2 hashing, JWT, reset tokens
│   │   ├── geo.py                # pure-Python geospatial math
│   │   ├── schemas.py            # Pydantic validation
│   │   ├── deps.py, errors.py, middleware/   # auth deps, error envelope, logging/rate-limit
│   │   ├── routers/              # auth, users, queries, datasets, results/jobs, reports, admin, system
│   │   └── services/
│   │       ├── nlp_understanding.py  # deterministic NL parsing (+LLM hook)
│   │       ├── gazetteer.py          # place → bbox
│   │       ├── agents.py             # SAR / Optical / Temporal / Fusion agents
│   │       ├── processing.py         # computational engine (all ops)
│   │       ├── satellite.py          # provider adapters
│   │       ├── indexing.py           # spatial+temporal+semantic (FAISS optional)
│   │       ├── pipeline.py           # end-to-end orchestration
│   │       ├── verification.py       # QA gate
│   │       ├── summarizer.py         # AI explanation
│   │       └── reporting.py          # GeoJSON/CSV/MD/HTML/PDF
│   ├── seed_data.py            # idempotent demo dataset + account seeding
│   ├── tests/                  # pytest: auth + pipeline suites
│   ├── .env.example
│   └── run.py, seed.py
├── frontend/
│   ├── src/
│   │   ├── api/client.js       # fetch wrapper + refresh login + WS + downloads
│   │   ├── context/            # auth + theme providers
│   │   └── components/         # layout, Logo.jsx, maps, charts, UI kit
├── frontend/public/            # logo.png (lockup) + logo-mark.png (favicon)
```

## ✅ Running the checks

```bash
# Backend tests (16 tests — auth, pipeline, reports, settings)
cd backend
.venv\Scripts\python -m pytest tests -q

# Quick API smoke (no pytest needed)
.venv\Scripts\python smoke_test.py

# Frontend production build
cd frontend
npm run build
```

## 📧 E-mail (Gmail SMTP)

Registration/resend OTPs, password-change codes and **"new sign-in" alerts**
(every successful login, including after MFA) are sent over SMTP. Gmail is the
default: `smtp.gmail.com:587` with STARTTLS.

```bash
# backend/.env
MAIL_ENABLED=auto                  # send as soon as credentials exist
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_STARTTLS=true
SMTP_USERNAME=you@gmail.com        # the Gmail mailbox that authenticates
SMTP_PASSWORD=xxxxxxxxxxxxxxxx     # Google App Password (spaces are stripped)
SMTP_FROM_NAME=SatQuery AI         # sender display name (branding)
LOGIN_NOTIFICATION_ENABLED=true    # "new sign-in" alerts (per-user opt-out too)
```

1. Turn on 2-Step Verification for the Google account.
2. Create an App Password: <https://myaccount.google.com/apppasswords>.
3. Paste it into `SMTP_PASSWORD` (and restart the backend).

Verify from the admin API:

```bash
curl -H "Authorization: Bearer <admin-token>" "http://localhost:8000/api/admin/mail/status?probe=true"
curl -X POST -H "Authorization: Bearer <admin-token>" "http://localhost:8000/api/admin/mail/test"
```

Without credentials (or when Gmail is unreachable) the app **degrades
gracefully**: OTP responses return `demo_code` and sign-in alerts are skipped,
so registration/login always keep working. Credentials live only in the
environment - they are never logged, returned by an API or shown in errors.

## 🔌 Connecting real providers

| Provider | Env vars | Notes |
|---|---|---|
| Gmail SMTP (transactional e-mail) | `SMTP_USERNAME`, `SMTP_PASSWORD` (App Password) | OTP verification + new sign-in alerts; `MAIL_ENABLED=auto` |
| Sentinel (Copernicus Data Space) | `SENTINEL_CLIENT_ID`, `SENTINEL_CLIENT_SECRET` | catalog search implemented (OData) |
| USGS Landsat (M2M) | `LANDSAT_API_KEY` | catalog search implemented |
| STAC Earth Search (key-free) | — | scene retrieval for “find images” queries |
| Google AI Studio (Gemini) | `GEMINI_API_KEY` | Optional Google Search-grounded research on `/api/queries/research` and `/understand` |
| Optional ML/geo | `LLM_API_KEY` | sets `DEMO_MODE=auto` to prefer real providers when keys are set |

Create a Gemini key in [Google AI Studio](https://aistudio.google.com/app/apikey),
then set `GEMINI_API_KEY=...` in `backend/.env` for a local backend, or in the
project-root `.env` when using Docker Compose. Restart the backend after setting
it. Research requests and parsed location/date context are sent to Gemini for
grounded research; the key is only used server-side. The feature is optional and
the existing curated research brief remains available when the key is absent or
the Gemini service cannot be reached.

When keys are absent, `DEMO_MODE=auto` keeps the demo catalog alive and the
frontend labels every result **Demo / simulated**.

## 📚 Documentation

- `docs/API.md` — every endpoint, request/response, errors, WebSocket.
- `docs/ARCHITECTURE.md` — services, data model, security model.
- `docs/CHANGE_ANALYSIS.md` — the historical Date 1 vs Date 2 change-analysis
  feature: architecture, pipeline internals, API contract, configuration,
  cost/scale notes and extension points.
- In-app **How to Use** page (sidebar) — onboarding, workflows, troubleshooting.
- Interactive API docs at `http://localhost:8000/docs`.

## 🧾 License

MIT — demo data (India/admin boundaries, rainfall, imagery footprints) are
simulated placeholders, never presented as real observations.
│   │   ├── components/         # layout, logo, ui kit, MapView (react-leaflet)
│   │   └── pages/              # Login (app entry), Register, Forgot/Reset, Dashboard,
│   │                           # Results, ResultDetail, History, Datasets, Saved,
│   │                           # Settings, HowToUse, ChangeAnalysis, NotFound
│   └── vite.config.js          # /api + /ws proxy -> localhost:8000
├── docs/API.md                 # full REST reference
├── docs/CHANGE_ANALYSIS.md     # Date 1 vs Date 2 change-analysis architecture
└── docker-compose.yml          # mongo + backend + frontend
```

## 🐳 Optional: PostgreSQL/PostGIS + Redis + MongoDB via Docker

```bash
docker compose up -d mongo        # just the legacy document store
docker compose up -d postgis redis mongo   # full auth stack
# then set in backend/.env:
#   AUTH_STORE=auto               # auto: Postgres when reachable, else legacy store
#   POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/satquery
#   REDIS_URL=redis://localhost:6379/0
# Note: psycopg + redis are optional (see requirements-postgres.txt). Without
# them the app runs the full auth flows on the legacy store / in-memory cache.
```

A full `docker compose up` (postgis + redis + mongo + backend + frontend) is
also provided.

## 🧠 How the pipeline works

```
User Query
  └─► NLP Query Understanding   (location, time, phenomenon, data type, analysis)
        └─► Agent Selection      (SAR / Optical / Temporal / Fusion + model)
              └─► Data Retrieval  (provider adapters: demo / realtime / STAC / Sentinel / Landsat)
                    └─► Processing (flood mapping, change, classification,
                                    object detection, time-series, fusion, terrain,
                                    live real-events for earthquakes/weather/climate)
                          └─► Verification (geometry, statistics, provenance)
                                └─► AI Summary  ──► persisted Job/Result/Query
                                          └─► download GeoJSON/CSV/MD/HTML/PDF
```

**Real-time branch:** phenomena backed by key-free public APIs are routed to
actual observations instead of the simulated engine — `earthquake` → USGS,
`weather` → Open-Meteo current+forecast, `drought`/climate → Open-Meteo archive.

WebSockets push live stage progress (`/ws/jobs/{job_id}`); REST exposes the
full CRUD for queries, results, saved analyses and settings.
