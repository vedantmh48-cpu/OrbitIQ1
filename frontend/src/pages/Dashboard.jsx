import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Send, Sparkles, ChevronRight, Radio, ArrowRight, FileSearch, Database, Zap, Boxes } from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import { Alert, Button, Card, SectionTitle } from "../components/ui.jsx";
import { Spinner } from "../components/ui.jsx";
import RealtimePanel from "../components/RealtimePanel.jsx";

const EXAMPLES = [
  "Show flood affected areas in Kerala in August 2024 using SAR data",
  "Detect deforestation change in the Amazon between 2021 and 2024",
  "Classify land cover in Punjab and find the dominant crop class",
  "Compute NDVI vegetation health for Punjab using Sentinel-2 optical data",
  "Analyse SAR backscatter intensity for the Kerala coast using Sentinel-1 radar data",
  "Show recent earthquakes in California",
  "What is the current weather in Mumbai?",
  "Fuse SAR and optical data to map floods in Kerala for August 2024"
];

export default function Dashboard() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") || "");
  const [understanding, setUnderstanding] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [autoRuns, setAutoRuns] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (!text.trim()) { setUnderstanding(null); return; }
    const t = setTimeout(async () => {
      try { setUnderstanding(await api.post("/api/queries/understand", { text: text.trim() })); }
      catch { /* preview errors are non-blocking */ }
    }, 450);
    return () => clearTimeout(t);
  }, [text]);

  // Deep-linking: if ?q= is present (e.g. from clicking a dataset card), run it once.
  useEffect(() => {
    const q = params.get("q");
    if (q && autoRuns === 0) {
      setAutoRuns(1);
      run(decodeURIComponent(q));
    }
    if (q && autoRuns > 0) {
      setParams({}, { replace: true });
    }
  }, [params]);

  const run = async q => {
    setError("");
    setRunning(true);
    try {
      const res = await api.post("/api/queries", { text: q || text });
      navigate(`/results/${res.result_id}?job=${res.job_id}&q=${encodeURIComponent(q || text)}`);
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  const submit = e => {
    e.preventDefault();
    if (!text.trim() || running) return;
    run(text);
  };

  const sure = (label, value) => (
    <div key={label} className="rounded-xl border border-space-700 bg-space-850/60 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-0.5 truncate text-sm font-medium text-slate-200">{value || <span className="text-slate-600">—</span>}</div>
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* greeting */}
      <div className="animate-fade-up">
        <div className="section-kicker">Natural-language satellite intelligence</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Welcome back, <span className="gradient-text">{user?.name?.split(" ")[0] || "analyst"}</span>
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Ask anything about the Earth in plain English — floods, crops, change, live earthquakes
          or weather. The agents handle the rest.
        </p>
      </div>

      {/* query box */}
      <form onSubmit={submit} className="card animate-fade-up !p-5" style={{ animationDelay: "0.05s" }}>
        <div className="relative">
          <Sparkles className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-accent" />
          <textarea
            rows={3}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder='Try: "Show flood affected areas in Kerala in August 2024 using SAR data"'
            className="input !pl-12 !py-3.5 resize-none"
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e); }}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-slate-500">Ctrl/⌘ + Enter to run</span>
          <Button type="submit" loading={running}>
            {running ? "Analyzing…" : "Run analysis"}
            {!running && <Send className="h-4 w-4" />}
          </Button>
        </div>
      </form>

      {error && <Alert type="error">{error}</Alert>}

      {understanding && (
        <Card className="animate-fade-in">
          <SectionTitle icon={<Sparkles className="h-4 w-4" />}>Query understanding</SectionTitle>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
            {sure("Location", understanding.location)}
            {sure("Date range", understanding.date_start ? `${understanding.date_start} → ${understanding.date_end}` : "Most recent")}
            {sure("Phenomenon", understanding.phenomenon)}
            {sure("Data type", understanding.data_type)}
            {sure("Analysis", understanding.requested_analysis)}
            {sure("Agent", understanding.agent)}
          </div>
        </Card>
      )}
{/* quick stats + examples */}
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="card animate-fade-up !p-5" style={{ animationDelay: "0.1s" }}>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-accent">
            <Database className="h-4 w-4" /> Start here
          </div>
          <div className="space-y-2">
            <Link to="/datasets" className="btn-ghost w-full justify-between !border-space-700">
              <span className="flex items-center gap-2"><Database className="h-4 w-4 text-accent" /> Browse the data catalogue</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/results" className="btn-ghost w-full justify-between !border-space-700">
              <span className="flex items-center gap-2"><FileSearch className="h-4 w-4 text-accent" /> View my analyses</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/geotools" className="btn-ghost w-full justify-between !border-space-700">
              <span className="flex items-center gap-2"><Boxes className="h-4 w-4 text-accent" /> GeoTools — indices & GeoTIFF</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            {[["11+", "datasets"], ["Live", "feeds"], ["4", "agents"]].map(([v, l]) => (
              <div key={l} className="rounded-xl border border-space-700 bg-space-850/40 px-2 py-2.5">
                <div className="text-base font-bold text-accent">{v}</div>
                <div className="text-[10px] uppercase tracking-wide text-slate-500">{l}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card animate-fade-up !p-5" style={{ animationDelay: "0.15s" }}>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-accent">
            <Zap className="h-4 w-4" /> Try an example
          </div>
          <div className="grid gap-2 sm:grid-cols-1 md:grid-cols-2">
            {EXAMPLES.map(ex => (
              <button
                key={ex}
                onClick={() => run(ex)}
                disabled={running}
                className="group flex items-start justify-between gap-2 rounded-xl border border-space-700 bg-space-850/40 px-3 py-2.5 text-left text-[13px] text-slate-300 transition hover:border-accent/50 hover:bg-space-850 hover:text-white disabled:opacity-60"
              >
                <span className="min-w-0">{ex}</span>
                <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600 transition group-hover:text-accent" />
              </button>
            ))}
          </div>
        </div>
      </div>

      {running && (
        <div className="card flex items-center gap-3 px-5 py-4">
          <Spinner className="h-5 w-5" />
          <div>
            <div className="text-sm font-medium text-slate-200">Running satellite pipeline…</div>
            <div className="text-xs text-slate-500">Understanding → agent → retrieval → processing → verification</div>
          </div>
        </div>
      )}

      <div className="scroll-mt-24">
        <SectionTitle icon={<Radio className="h-4 w-4" />}>Real-time section</SectionTitle>
        <RealtimePanel />
      </div>
    </div>
  );
}