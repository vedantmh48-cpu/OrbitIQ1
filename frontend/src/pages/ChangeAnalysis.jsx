import { Component, useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays, CheckCircle2, Crosshair, Download, FileDown,
  FileJson, FileText, Flame, GitCompareArrows, Layers, MapPin,
  Play, Ruler, Search, XCircle
} from "lucide-react";
import {
  api, downloadFile, formatNumber, getAccessToken, wsUrl
} from "../api/client.js";
import {
  Alert, Badge, Button, Card, SectionTitle, SimulatedBadge, Spinner, Toggle
} from "../components/ui.jsx";
import CompareSliderMap from "../components/CompareSliderMap.jsx";
import { renderMarkdown } from "../utils/markdown.js";
import { buildChangeAnalysisPdf } from "../utils/pdfExport.js";

const PROMPT_EXAMPLES = [
  "Show infrastructure change",
  "Track new building construction",
  "Monitor water body shrinkage",
  "Vegetation loss analysis"
];

const TECH_META = {
  ndvi: { label: "Vegetation (NDVI)", color: "#22c55e" },
  ndwi: { label: "Water (NDWI)", color: "#0ea5e9" },
  ndbi: { label: "Built-up (NDBI)", color: "#f97316" },
  cva: { label: "Change vector (CVA)", color: "#a855f7" }
};

const PIPELINE_STAGES = [
  ["geocode", "Geocoding location & AOI"],
  ["inventory", "Retrieving imagery inventory"],
  ["scene", "Building aligned scenes"],
  ["engine", "Running change detection"],
  ["render", "Rendering heatmap & composites"],
  ["synthesize", "Generating AI report"],
  ["saved", "Saving analysis"]
];

const MD_STYLES = `
  .md-h { color:#f1f5f9; font-weight:700; margin:.9rem 0 .35rem; line-height:1.25; }
  .md-h-1 { font-size:1.15rem; } .md-h-2 { font-size:1.02rem; }
  .md-h-3 { font-size:.92rem; } .md-h-4,.md-h-5,.md-h-6 { font-size:.88rem; }
  .md-p { color:#94a3b8; margin:.45rem 0; font-size:.85rem; line-height:1.6; }
  .md-list { color:#94a3b8; margin:.45rem 0; padding-left:1.25rem; font-size:.85rem; }
  .md-list li { margin:.16rem 0; }
  .md-code { background:#1e293b; border:1px solid #334155; color:#7dd3fc;
    border-radius:.3rem; padding:.05rem .35rem; font-size:.78rem; font-family:ui-monospace,monospace; }
  .md-link { color:#38bdf8; text-decoration:underline; }
  .md-quote { border-left:3px solid #38bdf8; background:#0f2237; color:#7dd3fc;
    padding:.45rem .8rem; border-radius:0 .5rem .5rem 0; margin:.6rem 0; font-size:.82rem; }
  .md-hr { border:0; border-top:1px solid #243348; margin:1rem 0; }
  .md-table-wrap { overflow-x:auto; margin:.6rem 0; }
  .md-table { border-collapse:collapse; width:100%; font-size:.8rem; }
  .md-table th,.md-table td { border:1px solid #243348; padding:.32rem .55rem;
    text-align:left; color:#94a3b8; }
  .md-table th { background:#101d33; color:#e2e8f0; font-weight:600; white-space:nowrap; }
  .md-table tr:nth-child(even) td { background:rgba(15,35,70,.25); }
`;

function defaultDates() {
  const now = new Date();
  const y2 = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
  const iso = d => d.toISOString().slice(0, 10);
  return { date1: "2015-01-01", date2: iso(y2) };
}

function MarkdownReport({ markdown }) {
  let html = "";
  try {
    html = renderMarkdown(markdown || "");
  } catch {
    html = "";
  }
  if (!html) {
    return (
      <pre className="max-h-96 whitespace-pre-wrap rounded-xl border border-space-700 bg-space-850/40 p-3 font-mono text-xs leading-relaxed text-slate-300">
        {markdown || "No report text available for this analysis."}
      </pre>
    );
  }
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Safe number formatter: never throws on missing/NaN data. */
function num(v, digits = 2, fallback = "—") {
  if (v === null || v === undefined || v === "") return fallback;
  const n = Number(v);
  if (Number.isNaN(n)) return fallback;
  return n.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  });
}

/** Key/value row used by the structured report. */
function Kv({ label, value, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-space-800 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className={`font-medium text-slate-200 ${mono ? "font-mono text-xs" : ""}`}>
        {value || "—"}
      </span>
    </div>
  );
}

/** Error boundary: a throwing section must never blank the whole page. */
class SectionBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm text-rose-200">
          <span className="font-semibold">This section could not be displayed.</span>{" "}
          {this.state.error.message}
          <button
            type="button"
            className="ml-3 underline hover:text-rose-100"
            onClick={() => this.setState({ error: null })}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function ProgressPanel({ progress, status, stage }) {
  const pct = progress ?? 0;
  const stageIdx = PIPELINE_STAGES.findIndex(s => s[0] === stage);
  return (
    <Card className="border-accent/30">
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionTitle icon={<GitCompareArrows className="h-4 w-4" />}>
          Change-analysis pipeline
        </SectionTitle>
        <Badge color="accent">{status === "failed" ? "Failed" : `${Math.round(pct)}%`}</Badge>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-space-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-fuchsia-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <ol className="mt-4 space-y-2">
        {PIPELINE_STAGES.map(([id, label], i) => {
          const done = stageIdx > i || status === "completed";
          const active = stageIdx === i && status === "running";
          return (
            <li key={id} className="flex items-center gap-2.5 text-sm">
              {done || status === "completed" ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : active ? (
                <Spinner className="h-4 w-4 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0 text-slate-600" />
              )}
              <span className={active ? "font-semibold text-cyan-300" : done ? "text-slate-300" : "text-slate-500"}>
                {label}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function TechTable({ breakdown }) {
  if (!breakdown?.length) return <p className="text-sm text-slate-500">No technique evidence available.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-space-700">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-space-700 bg-space-850/60 text-xs uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2 text-left font-semibold">Technique</th>
            <th className="px-3 py-2 text-right font-semibold">Gain</th>
            <th className="px-3 py-2 text-right font-semibold">Loss</th>
            <th className="px-3 py-2 text-right font-semibold">Mean Δ</th>
          </tr>
        </thead>
        <tbody>
          {breakdown.map(t => (
            <tr key={t.id || t.label} className="border-b border-space-800 last:border-0">
              <td className="px-3 py-2 text-slate-200">
                <span
                  className="mr-2 inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: (TECH_META[t.id] || {}).color || "#a855f7" }}
                />
                {t.label || t.id}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-amber-300">{num(t.gain_km2, 2)} km²</td>
              <td className="px-3 py-2 text-right font-mono text-xs text-sky-300">{num(t.loss_km2, 2)} km²</td>
              <td className="px-3 py-2 text-right font-mono text-xs text-slate-300">
                {Number(t.mean_delta) >= 0 ? "+" : ""}{num(t.mean_delta, 3)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HotspotTable({ hotspots }) {
  if (!hotspots?.length) return <p className="text-sm text-slate-500">No significant hotspots clustered.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-space-700">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-space-700 bg-space-850/60 text-xs uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2 text-left font-semibold">#</th>
            <th className="px-3 py-2 text-left font-semibold">Signal</th>
            <th className="px-3 py-2 text-right font-semibold">Area</th>
            <th className="px-3 py-2 text-left font-semibold">Center (lat, lng)</th>
            <th className="px-3 py-2 text-right font-semibold">Intensity</th>
          </tr>
        </thead>
        <tbody>
          {hotspots.slice(0, 10).map(h => (
            <tr key={h.rank} className="border-b border-space-800 last:border-0">
              <td className="px-3 py-2 font-mono text-xs text-slate-400">{h.rank}</td>
              <td className="px-3 py-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                  h.signal === "gain" ? "bg-amber-500/20 text-amber-300" : "bg-sky-500/20 text-sky-300"
                }`}>
                  {h.signal || "change"}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-slate-200">{num(h.area_km2, 3)} km²</td>
              <td className="px-3 py-2 font-mono text-xs text-slate-400">
                {num(h.center?.lat, 5)}, {num(h.center?.lng, 5)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-slate-300">{num(h.intensity, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function StructuredReport({ result }) {
  const und = result?.understanding || {};
  const stats = result?.stats || {};
  const summary = result?.summary || {};
  const highlights = Array.isArray(summary.highlights) ? summary.highlights : [];
  const techniques = result?.technique_breakdown || [];
  const hotspots = result?.hotspots || [];
  const meta = result?.metadata || {};
  const inv1 = meta.inventory_1 || {};
  const inv2 = meta.inventory_2 || {};

  const srcList = inv => {
    if (Array.isArray(inv.scenes) && inv.scenes.length) {
      return inv.scenes.map(s => s.id || s).join(", ");
    }
    return "synthetic demo scene";
  };
  const statusOf = inv =>
    Array.isArray(inv.scenes) && inv.scenes.length ? "real catalog metadata" : "simulated (demo raster)";

  return (
    <div className="space-y-6">
      {/* Overview */}
      <div>
        <h3 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-300">
          <Ruler className="h-3.5 w-3.5" /> Overview
        </h3>
        <div className="grid gap-x-8 sm:grid-cols-2">
          <div>
            <Kv label="Query" value={`“${und.query_text || "—"}”`} />
            <Kv label="Location" value={und.location} />
            <Kv label="Period" value={`${und.date_start || "—"} → ${und.date_end || "—"}`} />
            <Kv label="AOI area" value={`${num(stats.aoi_area_km2, 2)} km²`} />
            <Kv label="Changed area" value={`${num(stats.changed_area_km2, 2)} km²`} />
          </div>
          <div>
            <Kv label="Changed fraction" value={`${num(stats.pct_changed, 1)}%`} />
            <Kv label="Hotspots detected" value={num(stats.hotspot_count, 0)} />
            <Kv label="Dominant signal" value={stats.dominant_signal || "—"} />
            <Kv label="Mean / max intensity" value={`${num(stats.mean_abs_heat, 3)} / ${num(stats.max_heat, 3)}`} />
            <Kv label="Confidence" value={result.confidence != null ? `${Math.round(result.confidence * 100)}%` : "—"} />
          </div>
        </div>
      </div>

      {/* Key findings */}
      {highlights.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Key findings</h3>
          <ul className="space-y-1.5">
            {highlights.map((h, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <span>{h}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Evidence by technique</h3>
        <TechTable breakdown={techniques} />
      </div>

      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Change hotspots</h3>
        <HotspotTable hotspots={hotspots} />
      </div>

      {/* Provenance */}
      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Imagery provenance</h3>
        <div className="overflow-x-auto rounded-xl border border-space-700">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="border-b border-space-700 bg-space-850/60 text-xs uppercase tracking-wider text-slate-500">
                <th className="px-3 py-2 text-left font-semibold">Date</th>
                <th className="px-3 py-2 text-left font-semibold">Scene</th>
                <th className="px-3 py-2 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-space-800 last:border-0">
                <td className="px-3 py-2 font-mono text-xs text-slate-300">{und.date_start || "Date 1"}</td>
                <td className="px-3 py-2 text-xs text-slate-200">{srcList(inv1)}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{statusOf(inv1)}</td>
              </tr>
              <tr className="border-b border-space-800 last:border-0">
                <td className="px-3 py-2 font-mono text-xs text-slate-300">{und.date_end || "Date 2"}</td>
                <td className="px-3 py-2 text-xs text-slate-200">{srcList(inv2)}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{statusOf(inv2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Methodology / caveats */}
      {(summary.narrative || summary.disclaimer) && (
        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Methodology & caveats</h3>
          {summary.narrative && (
            <p className="text-sm leading-relaxed text-slate-300">{summary.narrative}</p>
          )}
          {summary.disclaimer && (
            <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/90">
              {summary.disclaimer}
            </p>
          )}
        </div>
      )}

      {/* AI narrative */}
      {result.report_md && (
        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">AI narrative report</h3>
          <MarkdownReport markdown={result.report_md} />
        </div>
      )}

      {/* Raw markdown fallback */}
      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">Raw report</h3>
        <details className="rounded-lg border border-space-700 bg-space-850/40">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-400">
            Show markdown source
          </summary>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed text-slate-400">
            {result.report_md || "—"}
          </pre>
        </details>
      </div>
    </div>
  );
}

export default function ChangeAnalysis() {
  const [caps, setCaps] = useState(null);
  const [mode, setMode] = useState("place");
  const [place, setPlace] = useState("Mumbai");
  const [lat, setLat] = useState("19.0760");
  const [lng, setLng] = useState("72.8777");
  const [buffer, setBuffer] = useState("1.0");
  const { date1, date2 } = useMemo(defaultDates, []);
  const [date1v, setDate1v] = useState(date1);
  const [date2v, setDate2v] = useState(date2);
  const [query, setQuery] = useState("Show infrastructure change");
  const [techniques, setTechniques] = useState([]);
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showMagnitude, setShowMagnitude] = useState(false);
  const [showHotspots, setShowHotspots] = useState(true);
  const [heatOpacity, setHeatOpacity] = useState(0.65);
  const pollRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/api/change-analysis/capabilities");
        setCaps(r);
      } catch { /* optional */}
    })();
  }, []);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (wsRef.current) { try { wsRef.current.close(); } catch { /* noop */ } }
  }, []);

  const stopWatchers = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (wsRef.current) { try { wsRef.current.close(); } catch { /* noop */ } wsRef.current = null; }
  };

  const finishResult = async resultId => {
    try {
      const r = await api.get(`/api/change-analysis/results/${resultId}`);
      setResult(r);
      setJob(prev => ({ ...(prev || {}), status: "completed", progress: 100,
        stage: "saved", result_id: resultId }));
    } catch (e) {
      setError(e.message || "Could not load the result.");
    } finally {
      setRunning(false);
      stopWatchers();
    }
  };

  const fail = message => {
    setError(message || "Change analysis failed.");
    setRunning(false);
    stopWatchers();
  };

  const pollJob = jobId => {
    pollRef.current = setInterval(async () => {
      try {
        const j = await api.get(`/api/change-analysis/jobs/${jobId}`);
        setJob(j);
        if (j.status === "completed") {
          if (pollRef.current) clearInterval(pollRef.current);
          if (j.result_id) await finishResult(j.result_id);
        } else if (j.status === "failed") {
          fail(j.message);
        }
      } catch (e) {
        fail(e.message || "Lost connection to the job.");
      }
    }, 1200);
  };

  const previewAoi = async () => {
    setPreviewBusy(true);
    setError("");
    try {
      const params = mode === "place"
        ? `q=${encodeURIComponent(place)}`
        : `coordinates=${parseFloat(lat).toFixed(5)},${parseFloat(lng).toFixed(5)}`;
      const bufferParam = buffer ? `&buffer_km=${parseFloat(buffer)}` : "";
      const r = await api.get(`/api/change-analysis/geocode?${params}${bufferParam}`);
      setPreview(r.aoi);
    } catch (e) {
      setError(e.message || "Geocoding failed.");
      setPreview(null);
    } finally {
      setPreviewBusy(false);
    }
  };

  const runAnalysis = async () => {
    setError("");
    setResult(null);
    setJob({ status: "queued", progress: 0, stage: "queued" });
    setRunning(true);
    try {
      const body = {
        location: mode === "place"
          ? { text: place }
          : { latitude: parseFloat(lat), longitude: parseFloat(lng) },
        date_1: date1v,
        date_2: date2v,
        query,
        ...(techniques.length ? { techniques } : {}),
        ...(mode === "coords" && buffer ? { buffer_km: parseFloat(buffer) } : {})
      };
      const r = await api.post("/api/change-analysis", body);
      try {
        wsRef.current = new WebSocket(wsUrl(r.job_id));
        wsRef.current.onmessage = ev => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "progress") setJob({ ...msg, id: r.job_id, status: "running" });
            if (msg.type === "complete") finishResult(msg.result_id);
            if (msg.type === "error") fail(msg.message);
          } catch { /* malformed frame */ }
        };
      } catch { /* REST polling covers it */ }
      pollJob(r.job_id);
    } catch (e) {
      fail(e.message || "Could not start the analysis.");
    }
  };

  const techToggle = id => {
    setTechniques(prev =>
      prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id]
    );
  };

  const downloadPdf = async () => {
    setError("");
    try {
      await downloadFile(`/api/reports/${result.id}/pdf`, `change-analysis-${result.id.slice(0, 8)}.pdf`);
    } catch {
      // Server-side PDF unavailable → build it entirely in the browser (jsPDF).
      try {
        await buildChangeAnalysisPdf(result);
      } catch {
        setError("PDF export failed — use the Report (.md) or a print from the browser instead.");
      }
    }
  };

  const imgUrl = kind => result
    ? `/api/change-analysis/results/${result.id}/images/${kind}.png?token=${encodeURIComponent(getAccessToken())}`
    : "";
  const bbox = result?.understanding?.bbox;
  const stats = result?.stats || {};
  const hotspots = result?.geojson || null;
  const capsTechs = caps?.techniques || [];

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <style>{MD_STYLES}</style>

      <div className="animate-fade-up">
        <div className="section-kicker">Historical satellite intelligence</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Change <span className="gradient-text">Analysis</span>
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Pick two dates and a place, describe what you care about, and SatQuery AI
          geocodes the AOI, aligns two scenes, runs spectral change detection
          (NDVI / NDBI / NDWI + change-vector analysis) and writes an
          evidence-backed, human-readable report.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {capsTechs.map(t => (
            <span key={t.id} className="chip !border-cyan-500/30 !text-cyan-300">{t.label}</span>
          ))}
          <span className="chip">{caps?.imagery_default === "demo" ? "Demo imagery tier" : "Auto imagery tier"}</span>
          <span className="chip">{caps?.llm_synthesis === "vision-llm" ? "Vision-LLM synthesis" : "Template synthesis"}</span>
        </div>
      </div>

      {error && <Alert type="error" title="Change analysis">{error}</Alert>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,380px)_1fr]">
        <Card className="self-start space-y-4 !p-4">
          <SectionTitle icon={<MapPin className="h-4 w-4" />}>Location & dates</SectionTitle>
          <div className="flex gap-1 rounded-xl border border-space-700 bg-space-850/60 p-1">
            {[["place", "Place name"], ["coords", "GPS coords"]].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  mode === id ? "bg-accent/15 text-accent" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === "place" ? (
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Place / address
              </label>
              <input
                value={place}
                onChange={e => setPlace(e.target.value)}
                placeholder="e.g. Mumbai, Kerala, Ho Chi Minh City…"
                className="input w-full"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Latitude</label>
                <input value={lat} onChange={e => setLat(e.target.value)} className="input w-full" inputMode="decimal" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Longitude</label>
                <input value={lng} onChange={e => setLng(e.target.value)} className="input w-full" inputMode="decimal" />
              </div>
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  AOI buffer (km)
                </label>
                <input value={buffer} onChange={e => setBuffer(e.target.value)} className="input w-full" type="number" min="0.1" max="50" step="0.1" />
              </div>
            </div>
          )}

          <Button variant="ghost" loading={previewBusy} onClick={previewAoi} className="w-full">
            <Search className="h-4 w-4" /> Preview AOI
          </Button>
          {preview && (
            <div className="rounded-xl border border-accent/25 bg-accent/5 px-3 py-2 text-xs text-slate-300">
              <div className="mb-1 flex items-center gap-1.5 font-semibold text-accent">
                <Crosshair className="h-3.5 w-3.5" /> {preview.name}
                <span className="text-slate-500">({preview.source})</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px] text-slate-400">
                <span>Area: {preview.area_km2.toFixed(2)} km²</span>
                <span>Center: {preview.center.lat.toFixed(4)}, {preview.center.lng.toFixed(4)}</span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Date 1</label>
              <input value={date1v} onChange={e => setDate1v(e.target.value)} type="date" min="1980-01-01" className="input w-full" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Date 2</label>
              <input value={date2v} onChange={e => setDate2v(e.target.value)} type="date" min="1980-01-01" className="input w-full" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Query prompt
            </label>
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              rows={3}
              className="input w-full resize-none"
              placeholder="e.g. Show infrastructure change"
            />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {PROMPT_EXAMPLES.map(p => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setQuery(p)}
                  className="chip !cursor-pointer hover:!border-accent/50 hover:!text-accent"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Techniques <span className="normal-case text-slate-600">(empty = auto from query)</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(TECH_META).map(([id, meta]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => techToggle(id)}
                  className={`chip transition ${
                    techniques.includes(id)
                      ? "!border-cyan-400/60 !bg-cyan-500/10 !text-cyan-300"
                      : "hover:!border-accent/40 hover:!text-accent"
                  }`}
                >
                  <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: meta.color }} />
                  {meta.label}
                </button>
              ))}
            </div>
          </div>

          <Button loading={running} onClick={runAnalysis} className="w-full">
            <Play className="h-4 w-4" /> Run change analysis
          </Button>
          <p className="text-center text-[11px] text-slate-600">
            Demo tier renders deterministic synthetic scenes; real STAC scene metadata is attached when reachable.
          </p>
        </Card>

        <div className="min-w-0 space-y-5">
          {running && (
            <ProgressPanel progress={job?.progress} status={job?.status} stage={job?.stage} />
          )}

          {!running && !result && !job && (
            <Card className="flex flex-col items-center justify-center px-6 py-20 text-center">
              <GitCompareArrows className="mb-4 h-12 w-12 text-slate-600" />
              <h3 className="text-base font-semibold text-slate-200">No analysis yet</h3>
              <p className="mt-1 max-w-md text-sm text-slate-500">
                Configure the location, dates and prompt on the left, then press
                <span className="font-semibold text-cyan-300"> Run change analysis</span>.
                The pipeline streams its progress and returns a side-by-side comparison,
                a change heatmap and a structured AI report.
              </p>
            </Card>
          )}

          {result && !running && (
            <SectionBoundary>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-bold text-white">{result.label}</h2>
                    <SimulatedBadge simulated={result.simulated} />
                    {conf != null && <Badge color="green">Confidence {Math.round(conf * 100)}%</Badge>}
                  </div>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {result.understanding?.date_start} → {result.understanding?.date_end}
                    <span className="text-slate-600">·</span>
                    Dominant signal: <span className="font-semibold uppercase text-amber-300">{stats.dominant_signal}</span>
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Button variant="ghost" onClick={() => downloadFile(`/api/change-analysis/results/${result.id}/report.md`, `change-report-${result.id.slice(0, 8)}.md`)}>
                    <FileText className="h-4 w-4" /> Report
                  </Button>
                  <Button variant="ghost" onClick={() => downloadFile(`/api/change-analysis/results/${result.id}/masks.geojson`, `change-cells-${result.id.slice(0, 8)}.geojson`)}>
                    <FileJson className="h-4 w-4" /> GeoJSON
                  </Button>
                  <Button variant="ghost" onClick={() => downloadFile(`/api/change-analysis/results/${result.id}/raster.tif`, `change-intensity-${result.id.slice(0, 8)}.tif`)}>
                    <Download className="h-4 w-4" /> GeoTIFF
                  </Button>
                  <Button variant="ghost" onClick={downloadPdf}>
                    <FileDown className="h-4 w-4" /> PDF
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                <Stat label="Changed area" value={`${formatNumber(stats.changed_area_km2, 2)} km²`} sub={`of ${formatNumber(stats.aoi_area_km2, 2)} km² AOI`} icon={<Ruler className="h-4 w-4" />} />
                <Stat label="Changed" value={`${formatNumber(stats.pct_changed, 1)}%`} sub={`${formatNumber(stats.changed_cells)} cells`} icon={<Flame className="h-4 w-4" />} />
                <Stat label="Hotspots" value={formatNumber(stats.hotspot_count)} sub="clustered by size" icon={<Crosshair className="h-4 w-4" />} />
                <Stat label="Mean intensity" value={stats.mean_abs_heat} sub={`max ${stats.max_heat}`} icon={<Layers className="h-4 w-4" />} />
                <Stat label="Index drift" value="NDVI/NBDI/NDWI"
                  sub={`${Number(stats.net_ndvi_delta).toFixed(3)} / ${Number(stats.net_ndbi_delta).toFixed(3)} / ${Number(stats.net_ndwi_delta).toFixed(3)}`}
                  icon={<GitCompareArrows className="h-4 w-4" />} />
              </div>

              {/* comparison map */}
              <Card className="!p-0 overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <Layers className="h-4 w-4 text-accent" /> Before / After comparison
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                    <Toggle checked={showHeatmap} onChange={setShowHeatmap} label="Heatmap" />
                    <Toggle checked={showMagnitude} onChange={setShowMagnitude} label="Magnitude" />
                    <Toggle checked={showHotspots} onChange={setShowHotspots} label="Hotspot cells" />
                    <label className="flex items-center gap-1.5 text-slate-400">
                      Opacity
                      <input
                        type="range" min={0.15} max={0.95} step={0.05}
                        value={heatOpacity}
                        onChange={e => setHeatOpacity(Number(e.target.value))}
                        className="w-24 accent-cyan-300"
                        aria-label="Overlay opacity"
                      />
                    </label>
                  </div>
                </div>
                <div className="h-[420px]">
                  <CompareSliderMap
                    bbox={bbox}
                    beforeUrl={imgUrl("before")}
                    afterUrl={imgUrl("after")}
                    heatmapUrl={imgUrl("heatmap")}
                    magnitudeUrl={imgUrl("magnitude")}
                    showHeatmap={showHeatmap}
                    showMagnitude={showMagnitude}
                    heatOpacity={heatOpacity}
                    hotspots={hotspots}
                    showHotspots={showHotspots}
                  />
                </div>
              </Card>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <SectionTitle icon={<Flame className="h-4 w-4" />}>Top change hotspots</SectionTitle>
                  <HotspotTable hotspots={result.hotspots} />
                </Card>
                <Card>
                  <SectionTitle icon={<Layers className="h-4 w-4" />}>Evidence by technique</SectionTitle>
                  <TechTable breakdown={result.technique_breakdown} />
                </Card>
              </div>

              <SectionBoundary>
                <Card>
                  <SectionTitle icon={<FileText className="h-4 w-4" />}>
                    Analysis report — full structured view
                  </SectionTitle>
                  <StructuredReport result={result} />
                </Card>
              </SectionBoundary>
            </SectionBoundary>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, icon }) {
  return (
    <div className="card p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        <span className="text-accent">{icon}</span> {label}
      </div>
      <div className="mt-1 text-base font-bold text-white">{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}