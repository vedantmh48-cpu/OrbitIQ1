# SatQuery AI — REST API Reference

Base URL: `http://localhost:8000`  ·  Interactive docs: `/docs` (Swagger) and `/redoc`.

All success responses are JSON. Errors use a consistent envelope:

```jsonc
{ "error": true, "detail": "Human-readable message", "code": "VALIDATION_ERROR" }
```

Authentication uses **Bearer** JWTs.

```
POST /api/auth/register          -> 201  { user, access_token, refresh_token }
POST /api/auth/login             -> 200  { user, access_token, refresh_token }
POST /api/auth/refresh           -> 200  { access_token }
POST /api/auth/logout            -> 200  { ok }
POST /api/auth/forgot-password   -> 200  { ok, message, demo_reset_link? }
POST /api/auth/reset-password    -> 200  { ok, message }
POST /api/auth/change-password   -> 200  { ok, message }        (auth)
```

## v1 Auth & Account Management (`/api/v1/auth`)

The v1 slice is the full identity vertical: role-based registration with
6-digit OTP e-mail verification, MFA (TOTP), persistent session tracking
(PostgreSQL/PostGIS + Redis with graceful fallbacks), and server-enforced
auto-logout.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Role-based sign-up (student / researcher / gis_analyst / organization). Government & Defense orgs force `mfa_required` and clamp idle time to 15 min. Returns `requires_email_verification`, `email`, `demo_code?` (demo mode only) | no |
| POST | `/api/v1/auth/verify-email` | `{ email, code }` – consumes the 6-digit OTP, sets `email_verified`, returns `user` + tokens | no |
| POST | `/api/v1/auth/verify-email/resend` | resend the registration OTP | no |
| POST | `/api/v1/auth/login` | `{ email, password }`. Returns tokens, or `mfa_required` / `mfa_setup_required` + `mfa_token` for MFA tiers. | no |
| POST | `/api/v1/auth/refresh` | `{ refresh_token }` – opaque refresh hashes are stored in `sessions` | no |
| POST | `/api/v1/auth/logout` | revoke the current session (by refresh token or bearer `sid`) | token |
| POST | `/api/v1/auth/heartbeat` | reset `last_seen_at` in the DB + session cache (idle timer) | token |
| GET | `/api/v1/auth/sessions` | list active sessions (device, IP, last seen, current flag) | token |
| DELETE | `/api/v1/auth/sessions/{session_id}` | revoke one session (never the current one) | token |
| POST | `/api/v1/auth/sessions/revoke-all` | sign out every other session | token |
| POST | `/api/v1/auth/change-password` | `{ current_password, new_password, confirm_password }` – 403 on wrong current password (rate-limited); dispatches password-change OTP | token |
| POST | `/api/v1/auth/change-password/verify` | `{ password_change_id, otp_code }` – commits the hash, updates `password_changed_at`, revokes all other sessions, broadcasts `password_changed` | token |
| POST | `/api/v1/auth/mfa/setup` | new TOTP secret + `otpauth://` URI | token |
| POST | `/api/v1/auth/mfa/verify` | `{ code }` – enables TOTP | token |
| POST | `/api/v1/auth/mfa/disable` | `{ code }` – disables TOTP | token |
| POST | `/api/v1/auth/mfa/challenge` | `{ mfa_token, code }` – completes a pending MFA login | no |
| PUT | `/api/v1/auth/inactivity-timeout` | `{ inactivity_timeout_minutes }` (5/15/30/60); clamped to 15 for gov/defense | token |

**Session enforcement** – every protected request resolves the `sid` claim in
the access token against the session cache/DB and verifies `expires_at` and
`last_seen_at` + `inactivity_timeout_minutes`. Revoked / expired / inactive
sessions return `401` with codes `SESSION_REVOKED`, `SESSION_EXPIRED`,
`SESSION_INACTIVE`.

**WebSocket** – `WS /ws/notifications/{user_id}?token=..&session_id=..`
delivers `session_revoked`, `password_changed` and `account_deleted` events so
other tabs/devices sign out immediately.

**Storage** – set `AUTH_STORE=auto` (default: PostgreSQL/PostGIS when
reachable, else the legacy document store), `POSTGRES_DSN`, `REDIS_URL`,
`REDIS_ENABLED`. Tables: `users`, `sessions`, `email_verifications`.

**E-mail delivery (Gmail SMTP)** – registration, resend and password-change
OTPs, plus a **"new sign-in" alert after every successful login (including a
completed MFA challenge)**, are delivered over SMTP. Defaults target Gmail
(`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, STARTTLS). Set `SMTP_USERNAME`
(the Gmail address) and `SMTP_PASSWORD` (a 16-character Google **App
Password**, spaces are stripped automatically); `MAIL_ENABLED=auto` (default)
sends as soon as both are present. Sender branding comes from
`SMTP_FROM_NAME` (default `SatQuery AI`).

* When SMTP is unconfigured (or a send fails) the OTP response contains
  `demo_code` instead and the alert is skipped - registration, login and MFA
  never fail because of mail problems.
* Only **verified** addresses receive sign-in alerts, and users can opt out
  with `PUT /api/users/settings` → `{"notifications": {"security_alerts": false}}`.
* Credentials are environment-only; the app password is never logged, returned
  by the API or embedded in an error message.

## Map Type Catalog & Dynamic Layers (`/api/v1/maps`)

A 32+ entry catalog covering general/core reference, statistical &
data-viz, environmental/scientific, navigation & property, and modern
digital & cognitive cartography. Every entry ships a MapLibre/Deck.gl
`layer_config`, legend metadata, permission tier and 3D/temporal flags.

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/maps/catalog?category=&q=` | Catalog (searchable + category filter). Hidden entries are tier-gated (e.g. `cadastral` requires analyst+). | token |
| GET | `/api/v1/maps/layers/{key}?bbox=&count=&time_index=&dynamic=` | Layer config + deterministic dynamic GeoJSON (dots, flow arcs, choropleth cells, marching-squares isolines, DEM grids). | token |

**Dynamic renderers** by `layer_config.overlay.type`:

| Overlay | Renderer | Geometry served |
|---|---|---|
| `heat` / `dots` / `symbols` / `time_series` | Deck.gl `HeatmapLayer` / `ScatterplotLayer` | Points |
| `flow` | Deck.gl `ArcLayer` | 3-vertex LineStrings (origin → mid → destination) |
| `cartogram` | Deck.gl `PolygonLayer` | Styled polygons |
| `choropleth` / `cadastral` / `mental` / `aerodata` | MapLibre vector fill+line | Server-colored polygons |
| `isarithmic` / `climate` / `bathymetric` | MapLibre line (isoline) | Marching-squares LineStrings w/ `level` + `color` |
| `dem` | MapLibre `raster-dem` terrain | Elevation grid points + Mapzen terrarium tiles |

The frontend `useMapStyle` + `MapLayerController` consume these contracts to
stage/stack layers with opacity + visibility controls, a `LegendPanel`, and a
`TimeSliderControl` for temporal frames.

---

## Index of endpoints

### System (public)
| Method | Path | Notes |
|---|---|---|
| GET | `/` | app info |
| GET | `/api/health` | status + storage backend + dataset count |
| GET | `/api/about` | capabilities + demo note |
| POST | `/api/contact` | contact form (`name`, `email`, `subject`, `message`) |

### Users / Settings  (auth required)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/users/me` | current profile |
| PUT | `/api/users/me` | update `{ name?, email? }` |
| GET | `/api/users/settings` | full settings object |
| PUT | `/api/users/settings` | partial update `{ theme?, map_preferences?, notifications?, default_satellite_source?, ... }` |
| DELETE | `/api/users/me` | delete account (cascades personal data) |

### Queries
| Method | Path | Notes |
|---|---|---|
| POST | `/api/queries` | `{ text, dataset_ids?, params? }` → runs pipeline → `{ job_id, query_id, result_id, status }` |
| POST | `/api/queries/understand` | `{ text }` → NLP slots only (no processing) |
| GET | `/api/queries/history?limit=` | user query history (desc) |
| GET | `/api/queries/history/{id}` | query + its result |

### Datasets
| Method | Path | Notes |
|---|---|---|
| GET | `/api/datasets?data_type=&q=&phenomenon=` | catalogue |
| GET | `/api/datasets/providers` | availability of demo/STAC/Sentinel/Landsat |
| POST | `/api/datasets/ingest` | (analyst+) register a dataset |
| GET | `/api/datasets/search` | live provider STAC search |
| DELETE | `/api/datasets/{id}` | (analyst+) delete non-demo dataset |

### Jobs & Results
| Method | Path | Notes |
|---|---|---|
| GET | `/api/jobs` / `/api/jobs/{id}` | job status / progress |
| GET | `/api/results` | list my results (desc) |
| GET | `/api/results/{id}` | full bundle (geojson, stats, charts, verification, summary) |
| DELETE | `/api/results/{id}` | delete |

### Saved analyses
| Method | Path | Notes |
|---|---|---|
| POST | `/api/saved` | `{ result_id, name?, notes? }` |
| GET | `/api/saved` | list |
| DELETE | `/api/saved/{id}` | remove |

### Geospatial / Remote-sensing tools
| Method | Path | Notes |
|---|---|---|
| GET | `/api/geospatial/capabilities` | advertise parser/index/synthesis capability flags |
| GET | `/api/geospatial/indexes` | NDVI/NDWI/NDBI definitions with band formulas |
| GET | `/api/geospatial/demo` | download a synthetic demo GeoTIFF (simulated) |
| GET | `/api/geospatial/demo/parse` | parse the demo GeoTIFF → CRS / EPSG / bounds / WKT / GeoJSON |
| POST | `/api/geospatial/parse` | multipart `.tif` upload → CRS / EPSG / bounds / footprint (no GDAL) |
| POST | `/api/geospatial/indexes/run?index=&location=` | compute a spectral index over a gazetteer AOI |

> Results include an `execution_trace`: `{ target_task, modality, sensors, tools[], steps[], uncertainties[] }` — the agentic chain that produced the analysis. Every modal capability is honestly labelled simulated.

### Reports
| Method | Path | Notes |
|---|---|---|
| GET | `/api/reports/{resultId}/geojson` | `application/geo+json` download |
| GET | `/api/reports/{resultId}/csv` | CSVs |
| GET | `/api/reports/{resultId}/markdown` | MD |
| GET | `/api/reports/{resultId}/html` | HTML |
| GET | `/api/reports/{resultId}/pdf` | PDF via ReportLab A4 layout |
| GET | `/api/reports/{resultId}/docx` | Google-Docs / MS Word compatible DOCX |
| GET | `/api/reports/{resultId}/google/status` | `{ available, google_doc_url, docx_available, pdf_available }` |
| POST | `/api/reports/{resultId}/google-doc` | start Google Docs publish → `{ authorization_url }` **or** `{ requires_setup, docx_endpoint }` |
| GET | `/api/reports/google/callback` | OAuth callback → redirects back to the frontend with `?docs=success&url=…` |

> **Google Docs:** full publishing requires `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
> / `GOOGLE_REDIRECT_URI` in `backend/.env`. Without them, the UI automatically falls
> back to the always-available `.docx` (which opens directly in Google Docs / Word).

### Admin  (admin role)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/health` | backend/db/collections counts |
| GET | `/api/admin/stats` | users/queries/results, agents & ops distribution |
| GET | `/api/admin/users` | all users |
| PATCH | `/api/admin/users/{id}` | update role/active |
| POST | `/api/admin/seed/demo` | idempotent re-seed |
| POST | `/api/admin/system/log-level` | adjust logger |
| GET | `/api/admin/mail/status` | secret-free SMTP config (host, port, transport, **masked** username, sender, templates). `?probe=true` also opens a real SMTP connection (EHLO/STARTTLS, no auth) and returns `connection` |
| POST | `/api/admin/mail/test` | send a test message (defaults to the calling admin's address); `?to=addr` overrides. Returns `ok`, `delivery`, `mail` - never the app password |

### WebSocket
```
WS  /ws/jobs/{job_id}?token=<access_token>
```
Messages: `{ type: "progress", stage, stage_name, progress }`,
`{ type: "complete", result_id, query_id }`, `{ type: "error", message }`.

---

## Example: run a natural-language query

```
POST /api/queries
Authorization: Bearer <access_token>
{ "text": "Show flood affected areas in Kerala in August 2024 using SAR data" }

-> 200 { "job_id": "...", "query_id": "...", "result_id": "...", "status": "completed" }
```

Then `GET /api/results/{result_id}` returns:

```jsonc
{
  "id": "...", "op": "flood-mapping", "label": "Flood Mapping",
  "confidence": 0.68,
  "stats": { "affected_area_km2": 3314.83, "estimated_population": 2714844, ... },
  "geojson": { "type": "FeatureCollection", "features": [ ... ] },
  "charts": { "timeseries": [...], "categories": [...], "histogram": [...] },
  "metadata": { "source": "DEMO", "simulated": true, "satellite": "Sentinel-1 C-SAR (simulated)", ... },
  "verification": { "status": "passed", "score": 0.7, "checks": [ ... ] },
  "summary": { "narrative": "...", "disclaimer": "These results are based on DEMO/simulated data ..." }
}
```

## Rate limits
`RATE_LIMIT_ENABLED=true` (default) → 240 req/min global, 30 req/min on auth
endpoints, per IP. Exceeded returns `429 { code: "RATE_LIMITED" }`.

## Roles
- `user` — default; full personal CRUD.
- `analyst` — can ingest datasets.
- `admin` — user management, seeding, stats, log-level.

## Status codes
`200/201` ok · `400` bad input · `401` unauthenticated/expired · `403` wrong
role/account inactive · `404` missing · `409` duplicate email · `422` validation
· `429` rate limited · `500` internal (surfaced generically; detail logged).

---

## Historical Change Analysis (`/api/change-analysis`)

The dedicated **Date 1 vs Date 2** location-change pipeline. Full contract,
payloads and configuration live in `docs/CHANGE_ANALYSIS.md`.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/change-analysis` | Enqueue a job. Body `{ location: {text} \| {latitude,longitude}, date_1, date_2, query, techniques?, buffer_km?, max_cells? }` → `202 {job_id, status:"running"}`. Poll the job endpoint or subscribe to `WS /ws/jobs/{job_id}`. | token |
| GET | `/api/change-analysis/capabilities` | Techniques catalogue, imagery tier, LLM synthesis mode. | token |
| GET | `/api/change-analysis/geocode` | `?q=place` or `?coordinates=lat,lng[&buffer_km=]` → `{aoi:{name,bbox,geojson,center,area_km2,source}, buffer_km}` | token |
| GET | `/api/change-analysis/jobs/{job_id}` | `{status, progress, stage, stage_name, message, result_id, query_id}` | token |
| GET | `/api/change-analysis/results/{result_id}` | Full bundle: `stats`, `charts`, `hotspots`, `technique_breakdown`, `layers`, `geojson`, `report_md`, `summary`, provenance. | token |
| GET | `/api/change-analysis/results/{id}/images/{kind}.png` | `before` \| `after` \| `heatmap` \| `magnitude` \| `change-mask`. Accepts Bearer **or** `?token=` (for `<img>`/`ImageOverlay`). | bearer/token |
| GET | `/api/change-analysis/results/{id}/raster.tif` | Change-intensity GeoTIFF (EPSG:4326 single band). | token |
| GET | `/api/change-analysis/results/{id}/masks.geojson` | Changed-cell detector grid (gain/loss polycells). | token |
| GET | `/api/change-analysis/results/{id}/report.md` | Structured Markdown analytical report. | token |

Change-analysis rows are stored in the standard `results` collection
(`op: "change-analysis"`), so they also appear under `/api/results`, take part
in History/Saved, and are exportable via `/api/reports/{id}/{geojson|csv|markdown|html|pdf|docx}`.

Example submit:

```bash
curl -X POST http://localhost:8000/api/change-analysis \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "location": {"text": "Mumbai"},
    "date_1": "2015-01-01",
    "date_2": "2020-01-01",
    "query": "Track new building construction"
  }'
# -> 202 {"job_id":"...","status":"running", ...}
```