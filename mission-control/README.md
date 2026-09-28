# 🛰️ Mission Control

A **self-contained** mission-ops console for the SatQuery AI platform — its own
frontend and backend live together in this folder, decoupled from the main app.

| Piece | Path | What it is |
|---|---|---|
| **Frontend** | `frontend/` | Zero-build console: plain HTML + handcrafted CSS + vanilla JS. No npm needed. |
| **Backend** | `backend/` | FastAPI REST + telemetry API (in-memory store, no database). Also serves the frontend. |
| **API docs** | `http://localhost:8100/docs` | Auto-generated Swagger UI. |

## Screens

- **Overview** — KPI cards, active-mission manifest, fleet strip, live alert feed.
- **Missions** — full lifecycle: create → queue → start → hold/resume → complete/abort/delete.
- **Fleet** — constellation status cards (orbit, link, battery, altitude, instruments, mini downlink trend).
- **Telemetry** — 2-second live polling view with an SVG chart and bus readouts.
- **Alerts** — consolidated feed with severity blocks and acknowledgement.

## Quick start

```bash
# 1) Backend
cd mission-control/backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run.py                   # -> http://127.0.0.1:8100

# 2) Open the console
#    http://127.0.0.1:8100   (served by the backend itself)
```

API only? `uvicorn app.main:app --reload --port 8100` (skip the `frontend/` dir
and the service still runs — a warning is logged and `/api/*` stays live).

## API

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | Service status |
| `GET`  | `/api/overview` | Aggregated KPIs for the home screen |
| `GET/POST` | `/api/missions` | List / create missions |
| `GET/PATCH/DELETE` | `/api/missions/{id}` | Read / command / remove a mission |
| `GET`  | `/api/satellites` | Fleet status |
| `GET`  | `/api/telemetry/{id}` | Live sample + rolling history (advances per poll) |
| `GET/PATCH` | `/api/alerts` | Alert feed / acknowledge (`{"acknowledged": true}`) |

### Mission lifecycle states

`planned → queued → in-progress ⇄ holding → completed` (or `aborted` at any point).

## Tests

```bash
cd mission-control/backend
.venv\Scripts\python -m pytest tests -q
```

## Frontend CSS architecture

The console ships a deliberate stylesheet stack (loaded in order):

```
css/reset.css       modern reset + element defaults, scrollbars
css/tokens.css      design tokens (colors, spacing, typography, dark/light themes)
css/base.css        application shell: sidebar, topbar, view grid, responsive
css/components.css  reusable components: cards, buttons, badges, tables, forms, modal, toasts
css/dashboard.css   view-specific layouts: overview, missions, fleet, telemetry, alerts
```

Theme toggle persists via `localStorage`; the UI is responsive from 320px up.

## Notes

- Telemetry is a **deterministic simulation** (smooth random-walk generator) so
  the console is demo-ready with no external live feeds — swap
  `app/store.py::push_telemetry` for a real downlink later.
- The backend binds `127.0.0.1:8100` by default (env: `MC_HOST`, `MC_PORT`) so it
  never collides with the main SatQuery backend (`8000`) or frontend (`5173`).