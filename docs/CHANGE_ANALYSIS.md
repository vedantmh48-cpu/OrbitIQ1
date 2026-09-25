# Historical Location & Infrastructure Change Analysis

A dedicated end-to-end feature inside SatQuery AI that answers **"what changed
between Date 1 and Date 2 at this place?"** using satellite-style imagery and an
AI-driven interpretation layer.

```
User inputs:  Date 1 · Date 2 · Location (place name | GPS coords) · Query prompt
                                                    │
                          ┌─────────────────────────▼──────────────────────────┐
                          │ 1. GEOCODING        gazetteer │ Nominatim │ coords │
                          │ 2. IMAGERY          STAC Earth Search (real)  +   │
                          │                     deterministic demo scenes     │
                          │ 3. CHANGE ENGINE    NDVI / NDBI / NDWI differenc- │
                          │                     ing + Change Vector Analysis +│
                          │                     hotspot clustering             │
                          │ 4. RENDER           before/after composites,      │
                          │                     signed heatmap, magnitude,    │
                          │                     intensity GeoTIFF, GeoJSON     │
                          │ 5. AI SYNTHESIS     query-aware VLM report        │
                          └─────────────────────────┬──────────────────────────┘
                                                    │
Outputs:  slider comparison · change heatmap · hotspot grid · structured report
```

The feature deliberately reuses the platform's existing contracts: results are
stored in the standard `results` collection (`op: "change-analysis"`), progress
streams on the same WebSocket (`/ws/jobs/{id}`), and the existing
PDF/DOCX/Markdown/HTML/Google-Doc export flows work unchanged.

---

## Why this design

| Requirement | Design decision |
|---|---|
| **Instant, offline, dependency-free operation** | The change engine is pure Python (stdlib only — `zlib`/`struct`/`math`). No GDAL, NumPy or Pillow is required, matching the rest of the codebase. |
| **Honest provenance** | Real STAC (Sentinel-2 L2A) scene **metadata** is retrieved when reachable and attached to the result; pixel-level rasters are deterministic *synthetic* scenes, always labelled `simulated`. The API/UI never present demo output as real observation. |
| **Meaningful proof on any AOI** | Synthetic landscape composition is *rank-normalised per scene*, so any lat/lon/place produces a realistic, reproducible mix of water / built-up / vegetation and a controlled evolution signal. |
| **Query-aware analysis** | The prompt is interpreted into an analysis lens ("building construction" → NDBI, "water shrinkage" → NDWI, "vegetation" → NDVI) that selects and ranks techniques. |
| **Async scale-out path** | `POST` enqueues a job and returns immediately; the pipeline runs in an executor and streams stage progress. The same runner can be routed to Celery/Redis for heavier workloads. |
| **Reusable with real satellites later** | The inventory stage already talks to STAC Earth Search (key-free). Swapping the synthetic raster tier for real COG downloads only touches `services/change_analysis/imagery.py`. |

---

## Module map (backend)

```
app/services/change_analysis/
├── geocoding.py   location → AOI bbox + GeoJSON
│                    coordinates (square buffer) · gazetteer · Nominatim fallback
├── imagery.py     per-date scene inventory
│                    STAC Earth Search (real metadata) · synthetic demo scenes
├── raster.py      dependency-free raster engine (the "GIS kernel")
│                    scene generator (rank-normalised land cover, band signatures)
│                    NDVI/NDWI/NDBI index stacks · differencing · CVA
│                    hotspot clustering (8-connectivity)
│                    PNG encoder · sign-coloured heatmap renderer · GeoTIFF writer
├── engine.py      high-level analysis: per-technique stats, charts, hotspots,
│                    changed-cell GeoJSON, artifact rendering
├── vlm.py         query interpretation + report synthesis
│                    deterministic Markdown template (always available)
│                    optional OpenAI-compatible Vision model (httpx, base64 inline)
└── pipeline.py    orchestrator: geocode → inventory → engine → render → synthesize
                    → persist result/query; async job runner + WS progress

app/routers/change_analysis.py   REST API (see next section)
app/schemas.py                   ChangeLocation / ChangeAnalysisRequest (validated)
app/config.py                    CHANGE_* settings (see .env.example)
```

## API contract

Base path `/api/change-analysis` · all endpoints require Bearer auth (image PNGs
additionally accept `?token=` so `<img>`/`ImageOverlay` can load them).

| Method | Path | Description |
|---|---|---|
| POST | `/api/change-analysis` | Enqueue a job. Body: `{ location: {text} \| {latitude,longitude}, date_1, date_2, query, techniques?, buffer_km?, max_cells? }`. Returns `{job_id, status:"running"}` (202). |
| GET | `/api/change-analysis/capabilities` | Engine flags, technique catalogue, imagery tier, LLM synthesis mode. |
| GET | `/api/change-analysis/geocode` | `?q=place` or `?coordinates=lat,lng[&buffer_km=]` → AOI preview `{aoi:{name,bbox,geojson,center,area_km2,source}, buffer_km}`. |
| GET | `/api/change-analysis/jobs/{job_id}` | Live job status (`status/progress/stage/stage_name/message/result_id`). |
| GET | `/api/change-analysis/results/{result_id}` | Full result bundle (stats, charts, hotspots, technique breakdown, layers, report_md, provenance). |
| GET | `/api/change-analysis/results/{id}/images/{kind}.png` | `before` · `after` · `heatmap` · `magnitude` · `change-mask`. |
| GET | `/api/change-analysis/results/{id}/raster.tif` | Change-intensity GeoTIFF (EPSG:4326, single band). |
| GET | `/api/change-analysis/results/{id}/masks.geojson` | Changed-cell detector grid (gain/loss polycells). |
| GET | `/api/change-analysis/results/{id}/report.md` | Structured Markdown analytical report. |

In addition the row exists under the standard `/api/results/{id}` and
`/api/reports/{id}/{geojson,csv,markdown,html,pdf,docx}` so existing history,
saved-analysis and export features pick it up automatically.

### Request example

```jsonc
{
  "location": { "text": "Mumbai" },          // or {"latitude":19.076,"longitude":72.8777}
  "date_1": "2015-01-01",
  "date_2": "2020-01-01",
  "query": "Track new building construction",
  "techniques": ["ndbi"],                     // optional; empty = auto from query
  "buffer_km": 1.0                            // used only for GPS coordinate input
}
```

Validation: `date_2 > date_1`, `date_1 ≥ 1980-01-01`, coordinates in range,
technique names from the catalogue (`ndvi|ndwi|ndbi|cva`), buffers ≤ 50 km.

### Result bundle (excerpt)

```jsonc
{
  "op": "change-analysis",
  "label": "Historical change — Mumbai",
  "stats": {
    "changed_area_km2": 12.431, "aoi_area_km2": 464.0, "pct_changed": 2.68,
    "changed_cells": 2886, "hotspot_count": 12,
    "net_ndvi_delta": -0.021, "net_ndbi_delta": 0.059, "net_ndwi_delta": -0.018,
    "dominant_signal": "ndbi", "window": "2015-01-01 → 2020-01-01"
  },
  "charts": { "categories": [...], "technique_bars": [...], "histogram": [...] },
  "hotspots": [{ "rank": 1, "signal": "gain", "area_km2": 0.85,
                 "center": {"lat": 19.0527, "lng": 72.9409}, "intensity": 0.23 }],
  "technique_breakdown": [{ "id": "ndbi", "gain_km2": 70.9, "loss_km2": 8.6, ... }],
  "geojson": { "type": "FeatureCollection", "features": [ /* changed cells */ ] },
  "report_md": "# Historical Change Analysis — Mumbai\n## What changed\n...",
  "layers": [ /* before / after / heatmap / magnitude ImageOverlay descriptors */ ],
  "simulated": true
}
```

---

## Pipeline internals

### 1. Geocoding
- **GPS coordinates** → square AOI from a `buffer_km` radius (longitude scaled
  by `cos(lat)`), returned as bbox + GeoJSON polygon + center + area.
- **Place name** → offline gazetteer first (deterministic, instant), then a
  best-effort Nominatim lookup (4 s timeout) for arbitrary addresses.
- Unknown names raise `LocationError` → HTTP 422.

### 2. Imagery inventory
- `CHANGE_IMAGERY_MODE=auto` queries STAC Earth Search (`sentinel-2-l2a`) for
  each date ±45 days, sorts by `eo:cloud_cover`, and keeps the real scene
  metadata (id, datetime, platform, cloud cover, preview href) as provenance.
- Pixel-level processing runs on **deterministic synthetic scenes** built by
  `raster.build_scene` — a rank-normalised landscape so every AOI yields a
  realistic water/built/vegetation/barren mix and a controlled evolution signal.
- Real COG download is the documented extension point (optional rasterio/GDAL
  tier, gated by the `raster_processed` flag in `imagery.py`).

### 3. Change engine
1. Two scenes are built on the same grid (aspect-ratio-corrected `cols×rows`
   respecting `CHANGE_MAX_CELLS`); date 2 applies urban expansion and
   water-line retreat to the same landscape.
2. Per-pixel indices: `NDVI`, `NDBI`, `NDWI` from physically-grounded band
   signatures (red/green/blue/nir/swir).
3. **Differencing** thresholds per technique (e.g. `|ΔNDBI| > 0.035` flags
   construction) plus **Change Vector Analysis** magnitude over the three
   indices, producing a signed intensity heatmap (loss → blues, gain → reds).
4. The union mask is clustered with 8-connectivity into **hotspots** (rank,
   area km², centroid, dominant sign, mean intensity).
5. Areas are integrated per cell with latitude-corrected cell size, so totals
   are true map areas over the synthetic grid.

### 4. Rendering (pure-stdlib encoders)
- `before.png` / `after.png` — true-colour composites (bilinear, 2% clip).
- `heatmap.png` — RGBα signed direction overlay for the map.
- `magnitude.png` — unsigned hot-intensity overlay.
- `change-mask.png` — translucent red union mask.
- `change-intensity.tif` — single-band EPSG:4326 GeoTIFF (row 0 = north) that
  opens in QGIS/ArcGIS/Jupyter; parses with the existing `geotools` reader.

### 5. AI synthesis
- Always-available **deterministic template**: renders a Markdown report with
  the analysis lens inferred from the query, "What changed" bullets,
  per-technique evidence table, top-8 hotspots and imagery provenance.
- Optional **Vision-Language refinement**: when `CHANGE_LLM_API_KEY` is set, an
  OpenAI-compatible `chat/completions` call (`CHANGE_LLM_BASE_URL` →
  OpenAI/Azure/OpenRouter/vLLM/Ollama) receives the metrics JSON plus the
  heatmap + before/after composites as inline base64 images and writes an
  "AI interpretation" section. Any failure degrades silently to the template.

---

## Configuration (backend/.env)

| Key | Default | Meaning |
|---|---|---|
| `CHANGE_ANALYSIS_ENABLED` | `true` | on/off the whole feature |
| `CHANGE_IMAGERY_MODE` | `auto` | `auto` → STAC metadata + demo rasters; `demo` → synthetic only |
| `CHANGE_MAX_CELLS` | `16900` | raster grid cell budget (~130×130) |
| `CHANGE_IMAGE_SIZE` | `360` | pixel edge of rendered PNG composites |
| `CHANGE_DEFAULT_BUFFER_KM` | `1.0` | AOI radius around a GPS point |
| `CHANGE_LLM_API_KEY` | *(empty)* | enables the vision-LLM tier (falls back to `LLM_API_KEY`) |
| `CHANGE_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI / Azure / OpenRouter / Ollama gateways |
| `CHANGE_LLM_MODEL` | `gpt-4o-mini` | vision-capable model id |
| `CHANGE_LLM_TIMEOUT_SECONDS` | `60` | vision call timeout |

## Frontend

New protected route `/change-analysis` (sidebar: **Change Analysis**):

1. **Inputs card** — place name or GPS coordinates, AOI preview button
   (calls `/geocode`), Date 1 / Date 2 pickers, a query-prompt box with example
   chips, and optional technique chips (NDVI / NDWI / NDBI / CVA).
2. **Live pipeline** — after `POST`, a stage stepper shows progress from
   WebSocket (`/ws/jobs/{job_id}`) with a 1.2 s REST poll as a safety net.
3. **Results**
   - Stat cards: changed area (km²), % changed, hotspot count, mean/max
     intensity, net NDVI/NDBI/NDWI drift.
   - **Before/after slider** — two `ImageOverlay` renders on dedicated Leaflet
     panes; the "after" pane is CSS-clipped by a draggable divider.
   - **Heatmap toggle** — signed change heatmap + magnitude overlays with an
     opacity slider; hotspot cells drawn as gain/loss GeoJSON; map legend.
   - **Evidence by technique** — gain/loss bars per index.
   - **Analytical report** — rendered Markdown + downloads (`.md`, GeoJSON,
     GeoTIFF, PDF/DOCX via the standard report endpoints).

## Cost & scale notes

| Tier | Behaviour | Cost |
|---|---|---|
| Demo (offline) | synthetic rasters, template report | $0, instant, no network |
| STAC metadata | ±2 HTTP POSTs per job to Earth Search | $0, key-free |
| Vision-LLM | 3 base64 PNGs (~360 px) + JSON per job | pennies per job at `gpt-4o-mini`; gate by `CHANGE_LLM_API_KEY` |
| Real COG processing (future) | rasterio windowed reads of Sentinel-2 COGs | egress from the catalog (free on STAC AWS), compute-bound |

Scale-out options: route `run_change_analysis_as_job` through Celery/Redis,
store artifacts in S3/MinIO instead of the local `data/change_analysis` dir,
and cap concurrent Vision calls with a token-bucket.

## Roadmap / extension points

- **Real raster tier** — `imagery.fetch_inventory` already returns a
  `raster_processed` flag; returning `true` when `rasterio` is importable and
  downloading the SCL-masked COG stack makes every number live.
- **More sensors** — add `sentinel-1-grd` SAR channels to `TECHNIQUES` (σ⁰
  differencing) and a `sar` lens to the query interpreter.
- **Segmentation-aware hotspots** — replace the cell flood-fill with
  superpixel/SLIC clustering when scikit-image is present.
- **ML change models** — plug a building-footprint or land-cover classifier into
  the `engine.run_change_analysis` evidence block; the VLM already consumes
  arbitrary metrics JSON.
- **Temporal smoothing** — composite ±N-day windows per date (already available
  in the STAC query window) to reduce seasonal false positives.