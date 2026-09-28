# SatQuery AI â€” Architecture

## System overview

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Frontend (React + Vite + Tailwind) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  Auth (login-first entry) Â· Dashboard (NL query) Â· Understanding panel      â”‚
â”‚  Results + interactive map (react-leaflet) + charts (recharts)           â”‚
â”‚  History Â· Datasets Â· Saved Â· Settings Â· How to Use                      â”‚
â”‚  WS client â†’ live pipeline progress                                      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                â”‚ REST (JWT)               â”‚ WebSocket /ws/jobs/{job_id}
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                        FastAPI application (backend)                     â”‚
â”‚  Middleware: CORS Â· request logging Â· sliding-window rate limiting       â”‚
â”‚  Routers: auth Â· users Â· queries Â· datasets Â· results/jobs Â· reports     â”‚
â”‚           Â· saved Â· admin Â· system                                       â”‚
â”‚  Service layer (pipeline): NL â†’ agent â†’ retrieval â†’ processing â†’         â”‚
â”‚   verification â†’ summary â†’ persistence                                   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
            â”‚                 â”‚                 â”‚
     Provider adapters    Storage backend    Geo engine (pure Python)
     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
     â”‚ demo (simulated)â”‚  â”‚ MongoDB (pymongo) â”‚  â”‚ deterministic field    â”‚
     â”‚ STAC Earth Searchâ”‚  â”‚ local JSON file  â”‚  â”‚ generation + area/stat â”‚
     â”‚ Sentinel/Copernicusâ”‚ â”‚ (offline fallback)â”‚  â”‚ computation            â”‚
     â”‚ Landsat/USGS    â”‚  â”‚                  â”‚  â”‚ (rasterio/GDAL/...      â”‚
     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚  optional when installed)â”‚
                                             â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Services

| Service | Responsibility | Optional deps |
|---|---|---|
| `services/nlp_understanding.py` | deterministic slot extraction (location/date/phenomenon/data-type/analysis) + agent vote + LLM hook | â€” |
| `services/gazetteer.py` | place-name â†’ bounding-box catalog (states, cities, countries) | â€” |
| `services/agents.py` | SAR / Optical / Temporal / Fusion agents â†’ processing plans | langgraph |
| `services/processing.py` | executes ops on seeded raster `FeatureCollection` grids, computes real area/statistics | numpy/scipy |
| `services/indexing.py` | spatial overlap + temporal overlap + semantic (trigram or model) + optional FAISS | faiss, sentence-transformers |
| `services/satellite.py` | provider adapter interface + demo/STAC/Sentinel/Landsat | httpx |
| `services/pipeline.py` | end-to-end orchestration + `execution_trace` (modality, tool chain, per-step results, uncertainties) | â€” |
| `services/verification.py` | geometry/statistical/provenance QA gate | â€” |
| `services/summarizer.py` | readable AI narrative + disclaimer | â€” |
| `services/reporting.py` | GeoJSON/CSV/Markdown/HTML/PDF/DOCX (pure-OOXML, Google-Docs-compatible) | reportlab |
| `services/google_docs.py` | real Google Docs publish via OAuth 2.0 (creates a Google Doc, stores the link on the result); degrades to `.docx` when unconfigured | google-api-python-client, google-auth |
| `services/geotools.py` | pure-Python GeoTIFF header/CRS/EPSG/bounds parsing, WKT + GeoJSON footprints, synthetic demo raster | â€” |
| `services/mailer.py` | SMTP delivery (Gmail default: `smtp.gmail.com:587` + STARTTLS) with a plain-text template registry that is HTML-ready; secret-free status/probe helpers; redacts credentials from errors | â€” |

## Data model

| Collection | Purpose | Key fields |
|---|---|---|
| `users` | accounts, PBKDF2 password hash, role, settings | `email`, `role`, `active`, `settings` |
| `sessions` | refresh-token registry (revoke on change/logout) | `refresh_jti`, `revoked` |
| `email_verifications` | hashed 6-digit OTPs (registration / password change) | `user_id`, `purpose`, `code_hash`, `expires_at`, `consumed` |
| `queries` | natural-language questions + parsed understanding | `text`, `understanding`, `agent`, `status` |
| `datasets` | catalogue (demo + user-ingested + real) | `data_type`, `bbox`, `simulated`, `series`, `grid` |
| `jobs` | async pipeline progress | `progress`, `stage`, `status` |
| `results` | full analysis output | `geojson`, `stats`, `charts`, `verification`, `summary`, `simulated` |
| `saved_analyses` | user pins | `result_id`, `name`, `notes` |
| `settings` | (merged into `users.settings` for simplicity) | â€” |
| `contacts` | contact-form messages | â€” |

Defaults in `config.py` choose MongoDB when reachable, else a local JSON file â€”
so the app is fully functional with or without a database service.

## Security

- **Passwords** â€” PBKDF2-HMAC-SHA256 (stdlib, 210k iterations, per-user salt).
- **JWTs** â€” HS256; short-lived **access** (2h) + long-lived **refresh** (30d,
  stored, revocable). Auto-refresh on the frontend with single retry.
- **Reset tokens** â€” single-use, hashed at rest, 30-minute TTL.
- **Protected routes** â€” `get_current_user` / `require_analyst` / `require_admin`
  dependencies; per-resource ownership checks for jobs/results/saved.
- **Validation** â€” Pydantic schemas with normalized error envelope (422).
- **Rate limiting** â€” in-memory sliding window per IP (adjustable).
- **Secrets** â€” env-driven; `.env.example` documents every option.
- **E-mail** â€” SMTP credentials (Gmail App Password) come from the environment
  only. The password is never logged, returned by an API or embedded in an
  error message (`services/mailer._redact`), `/api/admin/*` exposes only a
  masked mailbox, and delivery failures degrade to the local `demo_code`
  fallback instead of breaking registration/login/MFA. Sign-in alerts go to
  verified addresses only and respect `notifications.security_alerts`.
- **No fabricated data** â€” every demo result carries `simulated: true`; the UI
  labels it and summaries include a disclaimer.

## Frontend

- `api/client.js` â€” fetch wrapper (auto-refresh on 401), WebSocket helper,
  blob downloads, number/percent formatters.
- `context/` â€” `AuthProvider` (session restore, login/register/logout),
  `ThemeProvider` (dark/light, persisted).
- `components/MapView.jsx` â€” `react-leaflet` with tile baselayers, AOI bounds,
  severity/class colorization, optional extra layers.
- `pages/` â€” one file per route; `ProtectedRoute`/`GuestRoute` wrappers gate
  access; skeletons, empty states and alerts everywhere.

## Extending

**Add a provider:** subclass `services.satellite.BaseProvider`, register in
`_PROVIDER_FACTORIES`. When available, the pipeline prefers real providers.

**Add a processing op:** add a handler in `services/processing.py` and register
it in `run_operation`; wire an agent step in `services/agents.py`.

**Enable real geo/ML:** install the optional stack (`rasterio`, `geopandas`,
`faiss-cpu`, `sentence-transformers`, `reportlab`, `langgraph`) â€” all detected
at import time, so the app degrades gracefully when they are absent.
