import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Download, Save, Check, Map as MapIcon, ShieldCheck,
  FileText, FileDown, FileType2, X, ExternalLink, Sparkles, FileJson, FileSpreadsheet, FileCode2,
  ListTree, Radio
} from "lucide-react";
import {
  LineChart as ReLine, Line, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer,
  BarChart as RBar, Bar, Cell, CartesianGrid
} from "recharts";
import { api, downloadFile, formatNumber, formatPct, timeAgo, wsUrl } from "../api/client.js";
import { buildAnalysisPdf } from "../utils/pdfExport.js";
import { Alert, Badge, Button, Card, Skeleton, SimulatedBadge } from "../components/ui.jsx";
import MapView from "../components/MapView.jsx";

const OP_COLORS = {
  "flood-mapping": "#0ea5e9",
  "change-detection": "#f97316",
  "classification": "#22c55e",
  "object-detection": "#eab308",
  "time-series": "#a855f7",
  "fusion": "#8b5cf6",
  "terrain": "#a8a29e",
  "image-search": "#38bdf8",
  "real-events": "#f43f5e",
  ndvi: "#22c55e",
  ndwi: "#0ea5e9",
  ndbi: "#f97316",
  "sar-backscatter": "#fb923c"
};
const PIE_COLORS = ["#0ea5e9", "#f97316", "#22c55e", "#eab308", "#a855f7", "#38bdf8", "#f43f5e"];

export default function ResultDetail() {
  const { resultId } = useParams();
  const [params] = useSearchParams();
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(null);
  const [saved, setSaved] = useState(false);
  const [googleStatus, setGoogleStatus] = useState(null);
  const [googleModal, setGoogleModal] = useState(null);
  const [exporting, setExporting] = useState("");
  const [toast, setToast] = useState(null);
  const [baseLayer, setBaseLayer] = useState("Dark");
  const timerRef = useRef(null);

  const showToast = t => {
    setToast(t);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setToast(null), 8000);
  };

  // Google docs callback feedback (?docs=success&url=...)
  useEffect(() => {
    const docs = params.get("docs");
    if (docs === "success") {
      showToast({ type: "success", title: "Published to Google Docs", url: params.get("url") || "" });
    } else if (docs === "failed") {
      showToast({ type: "error", title: "Google Docs publish failed", msg: "The consent flow was interrupted or rejected. You can still download the .docx / PDF." });
    }
  }, [params]);

  useEffect(() => {
    const job = params.get("job");
    if (!job) return;
    try {
      const ws = new WebSocket(wsUrl(job));
      ws.onmessage = ev => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "progress" || msg.type === "complete") setProgress(msg);
        if (msg.type === "complete") setTimeout(() => ws.close(), 400);
      };
      return () => { try { ws.close(); } catch {} };
    } catch { /* ws unavailable — polling covers it */ }
  }, [params]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await api.get(`/api/results/${resultId}`);
        if (!cancelled) { setResult(data); setSaved(false); }
        try {
          const gs = await api.get(`/api/reports/${resultId}/google/status`);
          if (!cancelled) setGoogleStatus(gs);
        } catch { /* optional */ }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [resultId]);

  const save = async () => {
    try {
      await api.post("/api/saved", { result_id: result.id, name: result.label });
      setSaved(true);
      showToast({ type: "success", title: "Saved", msg: "Pinned to Saved analyses." });
    } catch (e) { setError(e.message); }
  };

  const publishToGoogleDocs = async () => {
    setExporting("google");
    try {
      const res = await api.post(`/api/reports/${result.id}/google-doc`);
      if (res.requires_setup) {
        setGoogleModal({ message: res.message, docx: res.docx_endpoint });
      } else if (res.authorization_url) {
        window.location.href = res.authorization_url;
        return;
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting("");
    }
  };

  const doDownload = async (fmt, ext) => {
    setExporting(fmt);
    try {
      await downloadFile(`/api/reports/${result.id}/${fmt}`, `orbitiq-${result.id.slice(0, 8)}.${ext}`);
      showToast({ type: "success", title: `${fmt.toUpperCase()} download started`, msg: "Check your browser downloads." });
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting("");
    }
  };

  /** Client-side PDF — generated entirely in the browser via jsPDF. */
  const downloadClientPdf = () => {
    setExporting("pdf-client");
    try {
      buildAnalysisPdf(result);
      showToast({ type: "success", title: "PDF generated in your browser", msg: "No server round-trip needed." });
    } catch (e) {
      setError(`Client PDF failed (${e.message}) — use the server PDF instead.`);
    } finally {
      setExporting("");
    }
  };
if (loading) return <ResultSkeleton />;
  if (error) return <div className="mx-auto max-w-3xl"><Alert type="error">Failed to load result: {error}</Alert></div>;
  if (!result) return <div className="mx-auto max-w-3xl"><Alert type="warn">This analysis is no longer available.</Alert></div>;

  const op = result.op || "flood-mapping";
  const opColor = OP_COLORS[op] || "#0ea5e9";
  const understanding = result.understanding || {};
  const summary = result.summary || {};
  const statsList = Object.entries(result.stats || {}).filter(([, v]) => v !== null && v !== "" && typeof v !== "object");

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {toast && (
        <div className={`animate-fade-up fixed bottom-5 right-5 z-[900] max-w-sm rounded-2xl border p-4 shadow-2xl ${
          toast.type === "success"
            ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
            : "border-rose-500/50 bg-rose-500/10 text-rose-300"}`}>
          <div className="flex items-center gap-2 font-semibold">{toast.title}</div>
          {toast.msg && <div className="mt-1 text-xs">{toast.msg}</div>}
          {toast.url && (
            <a href={toast.url} target="_blank" rel="noreferrer" className="btn-primary mt-2 !py-1.5 text-xs">
              Open in Google Docs <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      )}

      <Header
        result={result} op={op} opColor={opColor} understanding={understanding}
        saved={saved} onSave={save} baseLayer={baseLayer} setBaseLayer={setBaseLayer}
        onPublish={publishToGoogleDocs} exporting={exporting} doDownload={doDownload}
        onClientPdf={downloadClientPdf}
        googleDocUrl={googleStatus?.google_doc_url || result.google_doc_url}
        googleAvailable={googleStatus?.available}
      />
      {progress && progress.type !== "complete" && <ProgressBar msg={progress} />}
      {error && <Alert type="error">{error}</Alert>}
      {googleModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm" onClick={() => setGoogleModal(null)}>
          <div className="card relative my-8 w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
              <h2 className="text-lg font-bold text-white">Publish to Google Docs</h2>
              <button onClick={() => setGoogleModal(null)} className="rounded p-1.5 text-slate-400 hover:bg-space-800 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 p-5">
              <Alert type="warn" title="Not configured on this deployment">{googleModal.message}</Alert>
              <p className="text-sm text-slate-400">
                An administrator can enable one-click publishing by adding{" "}
                <code className="text-accent">GOOGLE_CLIENT_ID</code>,{" "}
                <code className="text-accent">GOOGLE_CLIENT_SECRET</code> and{" "}
                <code className="text-accent">GOOGLE_REDIRECT_URI</code> to{" "}
                <code className="text-accent">backend/.env</code>. Until then you can:
              </p>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" loading={exporting === "docx"} onClick={() => doDownload("docx", "docx")}>
                  <FileType2 className="h-4 w-4" /> Download .docx (opens in Google Docs)
                </Button>
                <Button variant="ghost" loading={exporting === "pdf"} onClick={() => doDownload("pdf", "pdf")}>
                  <FileDown className="h-4 w-4" /> Download PDF
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
<div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        {/* map */}
        <Card className="!p-0 overflow-hidden">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <MapIcon className="h-4 w-4 text-accent" /> Interactive map
            </div>
            <Badge color="slate">{result.geojson?.features?.length || 0} features</Badge>
          </div>
          <div className="h-[360px] sm:h-[420px] lg:h-[460px]">
            <MapView
              geojson={result.geojson}
              layers={result.layers}
              op={op}
              baseLayer={baseLayer}
              showLegend={op !== "time-series" && op !== "image-search"}
            />
          </div>
        </Card>

        <div className="space-y-4">
          {/* AI summary */}
          <Card>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-accent">
              <Sparkles className="h-4 w-4" /> AI summary
            </div>
            <p className="text-sm leading-relaxed text-slate-300">{summary.narrative || "Analysis complete."}</p>
            {summary.highlights && summary.highlights.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {summary.highlights.map(h => (
                  <li key={h} className="flex items-start gap-2 text-xs text-slate-400">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" /> {h}
                  </li>
                ))}
              </ul>
            )}
            {summary.disclaimer && (
              <p className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                {summary.disclaimer}
              </p>
            )}
          </Card>

          {/* key stats */}
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-semibold text-slate-200">Key statistics</div>
              <Badge color="green"><ShieldCheck className="h-3 w-3" /> {formatPct(result.confidence)} confidence</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {statsList.slice(0, 8).map(([k, v]) => <StatValue key={k} k={k} v={v} />)}
              {statsList.length === 0 && <div className="col-span-2 text-sm text-slate-500">No statistics recorded.</div>}
            </div>
          </Card>
        </div>
      </div>

      <ChartGrid result={result} opColor={opColor} />
      <ExecutionTracePanel result={result} />
      <VerificationAndMeta result={result} doDownload={doDownload} exporting={exporting} />
    </div>
  );
}
// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProgressBar({ msg }) {
  return (
    <div className="card flex items-center gap-3 px-4 py-3">
      <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
        <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="flex-1">
        <div className="text-xs font-medium text-slate-300">{msg.stage_name || "Working…"}</div>
        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-space-700">
          <div className="h-full rounded-full bg-gradient-to-r from-accent to-accent-deep transition-all" style={{ width: `${msg.progress || 0}%` }} />
        </div>
      </div>
      <span className="text-xs text-slate-500">{msg.progress || 0}%</span>
    </div>
  );
}

function Header({ result, op, opColor, understanding, saved, onSave, baseLayer, setBaseLayer, onPublish, exporting, doDownload, onClientPdf, googleDocUrl, googleAvailable }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-500" style={{ fontFamily: "monospace" }}>{result.id.slice(0, 8)}</span>
            <Badge color="slate">{op}</Badge>
            <SimulatedBadge simulated={result.simulated ?? true} />
          </div>
          <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">{result.label || "Analysis"}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {understanding.location || "Global"}
            {understanding.date_start && ` · ${understanding.date_start} → ${understanding.date_end || "now"}`}
            {result.created_at && <span className="text-slate-500"> · {timeAgo(result.created_at)}</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={baseLayer}
            onChange={e => setBaseLayer(e.target.value)}
            className="input !w-auto !py-2 text-xs"
            aria-label="Base layer"
          >
            <option>Dark</option>
            <option>Satellite</option>
            <option>Light</option>
          </select>
          <Button variant="ghost" onClick={() => doDownload("pdf", "pdf")} loading={exporting === "pdf"} className="!px-3 text-xs">
            <FileDown className="h-4 w-4" /> PDF
          </Button>
          {googleDocUrl ? (
            <a href={googleDocUrl} target="_blank" rel="noreferrer" className="btn-ghost border-emerald-500/40 !px-3 !py-2 text-xs text-emerald-400 hover:text-emerald-300">
              <FileText className="h-4 w-4" /> Open in Google Docs <ExternalLink className="h-3 w-3" />
            </a>
          ) : (
            <Button variant="primary" onClick={onPublish} loading={exporting === "google"} className="!px-3 !py-2 text-xs">
              <FileText className="h-4 w-4" /> Publish to Google Docs
            </Button>
          )}
          <Button variant="ghost" onClick={onSave} className="!px-3 !py-2 text-xs">
            {saved ? <><Check className="h-4 w-4 text-emerald-400" /> Saved</> : <><Save className="h-4 w-4" /> Save</>}
          </Button>
        </div>
      </div>

      {/* export strip */}
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border px-3 py-2.5">
        <span className="mr-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <Download className="h-3.5 w-3.5" /> Export
        </span>
        {[
          ["docx", "docx", "DOCX", FileType2],
          ["pdf", "pdf", "PDF", FileDown],
          ["markdown", "md", "Markdown", FileCode2],
          ["html", "html", "HTML", FileCode2],
          ["geojson", "geojson", "GeoJSON", FileJson],
          ["csv", "csv", "CSV", FileSpreadsheet]
        ].map(([fmt, ext, label, Icon]) => (
          <button
            key={fmt}
            onClick={() => doDownload(fmt, ext)}
            disabled={exporting}
            className="chip !cursor-pointer hover:border-accent hover:text-accent"
            title={`Download ${label}`}
          >
            <Icon className="h-3 w-3" /> {label}
          </button>
        ))}
        <button
          onClick={onClientPdf}
          disabled={exporting}
          className="chip !cursor-pointer hover:border-accent hover:text-accent"
          title="Generate the PDF directly in your browser"
        >
          <FileDown className="h-3 w-3" /> PDF (in-browser)
        </button>
        {!googleAvailable && !googleDocUrl && (
          <span className="ml-auto text-[11px] text-slate-600">Google Docs publishing needs setup — the .docx opens in Google Docs.</span>
        )}
      </div>
    </div>
  );
}
function StatValue({ k, v }) {
  const pretty = typeof v === "number"
    ? (String(k).includes("km") ? formatNumber(v, 2) : formatNumber(v))
    : String(v);
  return (
    <div className="rounded-xl border border-space-700 bg-space-850/60 px-3 py-2">
      <div className="truncate text-[10px] font-semibold uppercase tracking-wider text-slate-500">{k.replace(/_/g, " ")}</div>
      <div className="truncate text-sm font-bold text-slate-100" title={pretty}>{pretty}</div>
    </div>
  );
}

function ChartGrid({ result, opColor }) {
  const charts = [
    { title: "Time series", data: result.charts?.timeseries, kind: "line", color: opColor },
    { title: "Categories", data: result.charts?.categories, kind: "bar", color: opColor },
    { title: "Value distribution", data: result.charts?.histogram, kind: "hist", color: opColor }
  ];
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {charts.map(c => <ChartCard key={c.title} title={c.title} data={c.data} kind={c.kind} color={c.color} />)}
    </div>
  );
}

function ChartCard({ title, data, kind, color }) {
  const rows = (data || []).filter(d => d && (d.value != null || d.count != null));
  if (!rows.length || rows.every(r => Number(r.value ?? r.count ?? 0) === 0)) {
    return (
      <Card>
        <div className="mb-2 text-sm font-semibold text-slate-200">{title}</div>
        <div className="flex h-44 items-center justify-center text-sm text-slate-500">No data for this view</div>
      </Card>
    );
  }
  const isHist = kind === "hist";
  return (
    <Card>
      <div className="mb-2 text-sm font-semibold text-slate-200">{title}</div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          {kind === "line" ? (
            <ReLine data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} tickFormatter={v => String(v).slice(0, 10)} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
              <RTooltip contentStyle={{ background: "#0d1729", border: "1px solid #243a61", borderRadius: 8 }} />
              <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
            </ReLine>
          ) : kind === "bar" ? (
            <RBar data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 10 }} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
              <RTooltip contentStyle={{ background: "#0d1729", border: "1px solid #243a61", borderRadius: 8 }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {rows.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Bar>
            </RBar>
          ) : (
            <RBar data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey={isHist ? "bucket" : "name"} tick={{ fill: "#64748b", fontSize: 10 }} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
              <RTooltip contentStyle={{ background: "#0d1729", border: "1px solid #243a61", borderRadius: 8 }} />
              <Bar dataKey="count" fill={color} radius={[4, 4, 0, 0]} />
            </RBar>
          )}
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
function ExecutionTracePanel({ result }) {
  const trace = result.execution_trace || {};
  const modality = result.modality || {};
  const steps = trace.steps || [];
  if (!steps.length && !modality.label) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <Card>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <ListTree className="h-4 w-4 text-accent" /> Execution trace
        </div>
        <div className="mb-3 rounded-xl border border-space-700 bg-space-850/40 px-3 py-2 text-sm">
          <span className="text-slate-500">Target task: </span>
          <span className="font-medium text-slate-200">{trace.target_task || result.label || "Analysis"}</span>
        </div>
        <ol className="relative space-y-3 border-l border-space-700 pl-5">
          {steps.map(s => {
            const ok = s.result !== null && s.result !== undefined;
            return (
              <li key={s.step || s.tool} className="relative">
                <span className={`absolute -left-[27px] flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                  ok ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                }`}>
                  {ok ? "✓" : "✕"}
                </span>
                <div className="text-sm">
                  <span className="font-semibold text-slate-100">Step {s.step} — {s.tool}</span>
                  <span className="ml-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{s.op}</span>
                </div>
                <div className="mt-0.5 text-xs text-slate-400">{s.detail}</div>
                {s.result && s.result.features != null && (
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    → {s.result.features} features{s.result.label ? ` · ${s.result.label}` : ""}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {trace.uncertainties?.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-amber-300">Uncertainty & limitations</div>
            <ul className="space-y-1 text-xs text-amber-200/80">
              {trace.uncertainties.map((u, i) => <li key={i}>• {u}</li>)}
            </ul>
          </div>
        )}
      </Card>

      <div className="space-y-4">
        <Card>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Radio className="h-4 w-4 text-accent" /> Sensor modality
          </div>
          <div className="text-sm font-medium text-slate-100">{modality.label || "—"}</div>
          {modality.sensors?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {modality.sensors.map(s => <span key={s} className="chip !text-[11px]">{s}</span>)}
            </div>
          )}
          {modality.constraints && (
            <p className="mt-3 text-xs leading-relaxed text-slate-400">{modality.constraints}</p>
          )}
        </Card>
        <Card>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Sparkles className="h-4 w-4 text-accent" /> Key findings
          </div>
          <ul className="space-y-1.5">
            {(result.summary?.findings?.length ? result.summary.findings : result.summary?.highlights || []).map((h, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" /> {h}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function VerificationAndMeta({ result, doDownload, exporting }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <ShieldCheck className="h-4 w-4 text-accent" /> Verification report
        </div>
        {(result.verification?.checks || []).map(c => (
          <div key={c.name} className="mb-1.5 flex items-start gap-2 text-sm">
            <span
              className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                c.level === "passed" ? "bg-emerald-500/20 text-emerald-400" :
                c.level === "warning" ? "bg-amber-500/20 text-amber-400" : "bg-rose-500/20 text-rose-400"
              }`}
            >
              {c.level === "passed" ? "✓" : c.level === "warning" ? "!" : "✕"}
            </span>
            <span>
              <span className="font-medium text-slate-300">{c.name}:</span>{" "}
              <span className="text-slate-400">{c.detail}</span>
            </span>
          </div>
        ))}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-200">Dataset & model metadata</div>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <MetaX label="Model" value={result.metadata?.model} />
          <MetaX label="Satellite" value={result.metadata?.satellite} />
          <MetaX label="Resolution" value={result.metadata?.resolution} />
          <MetaX label="Data type" value={result.metadata?.data_type} />
          <MetaX label="Source" value={result.metadata?.source} />
          <MetaX label="Provenance" value={result.metadata?.simulated ? "Simulated demo" : "Real catalogue"} />
        </div>
        {result.metadata?.note && (
          <p className="mt-3 rounded-lg border border-space-700 bg-space-850/60 px-3 py-2 text-xs text-slate-400">
            {result.metadata.note}
          </p>
        )}
      </Card>
    </div>
  );
}

function MetaX({ label, value }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-slate-300">{value || "—"}</div>
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="flex items-center gap-3">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-5 w-24" />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Skeleton className="h-[460px] rounded-2xl" />
        <div className="space-y-4">
          <Skeleton className="h-36 rounded-2xl" />
          <Skeleton className="h-52 rounded-2xl" />
        </div>
      </div>
    </div>
  );
}