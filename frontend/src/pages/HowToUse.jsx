import { useState } from "react";
import { BookOpen, MousePointerClick, Search, Database, Sparkles, Map as MapIcon, FileDown, HelpCircle, Wrench, MessageSquareText } from "lucide-react";

const SECTIONS = [
  {
    id: "start",
    icon: MousePointerClick,
    title: "Getting started",
    body: "Create an account (or use the demo accounts shown on the sign-in screen). The demo catalogue — 11 clearly labelled simulated datasets covering SAR, Optical, DEM, Vector, Time-Series and Tabular data — is seeded automatically so everything works instantly with no API keys."
  },
  {
    id: "query",
    icon: MessageSquareText,
    title: "Writing queries",
    body: "On the dashboard, type a natural-language question. The NLP layer extracts location, date range, phenomenon, data type and requested analysis. Examples: “Show flood affected areas in Kerala in August 2024 using SAR data”, “Classify land cover in Punjab”, “Analyse urban expansion in Bengaluru 2015–2024”."
  },
  {
    id: "pipeline",
    icon: Sparkles,
    title: "How the pipeline works",
    body: "1) NLP understanding → 2) agent selection (SAR / Optical / Temporal / Fusion) → 3) dataset retrieval → 4) spatial/temporal analysis → 5) verification (geometry, statistics, provenance) → 6) AI summary → 7) persisted result with downloadable report."
  },
  {
    id: "map",
    icon: MapIcon,
    title: "Maps & results",
    body: "Results open on an interactive map (dark/satellite/streets baselines), with feature legend colouring by severity or class, plus time-series, category and histogram charts, key statistics, confidence and a verification report."
  },
  {
    id: "reports",
    icon: FileDown,
    title: "Reports, PDF & Google Docs",
    body: "Every analysis can be exported as GeoJSON, CSV, Markdown, HTML, DOCX or PDF (server-side via ReportLab, or generated instantly in your browser). The “Publish to Google Docs” button creates a real Google Document in your Drive when the admin has configured GOOGLE_CLIENT_ID — otherwise the same button hands you a .docx that opens directly in Google Docs / Word, so the workflow never breaks. Exports carry the data-provenance notice: demo results are simulated and must never be used for operational decisions."
  },
  {
    id: "datasets",
    icon: Database,
    title: "Supported datasets & GeoTools",
    body: "Optical (Sentinel-2, Landsat), SAR (Sentinel-1), DEM (SRTM), Vector (boundaries), Time-Series (MODIS LST) and Tabular (rain records). The GeoTools workshop adds a spectral-index engine (NDVI / NDWI / NDBI), SAR backscatter σ⁰ analysis, and a pure-Python GeoTIFF parser that extracts EPSG/CRS, bounds and WKT/GeoJSON footprints from uploaded .tif headers. Connect real providers via SENTINEL_CLIENT_ID, LANDSAT_API_KEY or STAC to replace simulated data with real retrievals."
  },
  {
    id: "troubleshoot",
    icon: HelpCircle,
    title: "Troubleshooting",
    body: "• No result? Try restating the location/date. • “Provider unavailable” — configured real providers require keys in backend/.env. • Expired session? Sign in again. • Performance slow? The demo grid caps cells per analysis. • Check backend/data/satquery.log for details."
  },
  {
    id: "settings",
    icon: Wrench,
    title: "Settings",
    body: "Under Settings you can update your profile, change the password, toggle dark/light theme, set map and data defaults, manage notification preferences and delete your account."
  }
];

export default function HowToUse() {
  const [open, setOpen] = useState("start");
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><BookOpen className="h-6 w-6 text-accent" /> How to Use</h1>
        <p className="mt-1 text-sm text-slate-400">A step-by-step guide to OrbitIQ.</p>
      </div>

      <div className="space-y-2">
        {SECTIONS.map(s => (
          <div key={s.id} className={`card overflow-hidden transition ${open === s.id ? "border-accent/50" : ""}`}>
            <button
              className="flex w-full items-center gap-3 px-4 py-3 text-left"
              onClick={() => setOpen(open === s.id ? "" : s.id)}
            >
              <s.icon className="h-5 w-5 shrink-0 text-accent" />
              <span className="flex-1 font-semibold text-slate-100">{s.title}</span>
              <span className="text-slate-500">{open === s.id ? "−" : "+"}</span>
            </button>
            {open === s.id && (
              <div className="animate-fade-in border-t border-space-700 px-4 py-3 text-sm leading-relaxed text-slate-300">
                {s.body}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="card p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-accent"><Search className="h-4 w-4" /> Example queries</div>
        <ul className="mt-3 space-y-2 text-sm text-slate-300">
          <li>• “Show flood affected areas in Kerala in August 2024 using SAR data”</li>
          <li>• “Detect deforestation change in the Amazon between 2021 and 2024”</li>
          <li>• “Classify land cover in Punjab and find the dominant class”</li>
          <li>• “Analyse the urban expansion trend in Bengaluru from 2015 to 2024”</li>
          <li>• “Fuse SAR and optical to map floods in Kerala in August 2024”</li>
        </ul>
      </div>
    </div>
  );
}