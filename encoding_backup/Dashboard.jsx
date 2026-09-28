import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import {
  Send, Sparkles, ChevronRight, Radio, ArrowRight, FileSearch, Database,
  Zap, Boxes, Layers, FolderHeart, GitCompareArrows, Bell, Activity,
  CheckCircle2, Clock, LineChart, CalendarDays
} from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useNotifications } from "../context/NotificationContext.jsx";
import { Alert, Button, Card, SectionTitle, StatCard } from "../components/ui.jsx";
import { Spinner } from "../components/ui.jsx";
import RealtimePanel from "../components/RealtimePanel.jsx";

const EXAMPLES = [
  "Show flood affected areas in Kerala in August 2024 using SAR data",
  "Detect deforestation change in the Amazon between 2021 and 2024",
  "Classify land cover in Punjab and find the dominant crop class",
  "Compute NDVI vegetation health for Punjab using Sentinel-2 optical data",
  "Show recent earthquakes in California",
  "What is the current weather in Mumbai?",
  "Fuse SAR and optical data to map floods in Kerala for August 2024",
  "Analyse SAR backscatter intensity for the Kerala coast using Sentinel-1 radar data"
];

const QUICK_ACTIONS = [
  { to: "/datasets", label: "Browse catalogue", hint: "Demo + live satellite data", icon: Database, accent: "text-accent", ring: "from-accent/15 to-accent/0" },
  { to: "/results", label: "My analyses", hint: "Rerun or export reports", icon: FileSearch, accent: "text-emerald-400", ring: "from-emerald-500/15 to-emerald-500/0" },
  { to: "/geotools", label: "GeoTools", hint: "NDVI / NDWI / GeoTIFF", icon: Boxes, accent: "text-violet-400", ring: "from-violet-500/15 to-violet-500/0" },
  { to: "/change-analysis", label: "Change analysis", hint: "Compare two dates", icon: GitCompareArrows, accent: "text-amber-400", ring: "from-amber-500/15 to-amber-500/0" }
];

export default function Dashboard() {
  const { user } = useAuth();
  const { items: notifications, markRead, markAllRead } = useNotifications();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") || "");
  const [understanding, setUnderstanding] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [autoRuns, setAutoRuns] = useState(0);
  const [stats, setStats] = useState(null);
  const navigate = useNavigate();

  // Home stats â€” derived from the same endpoints the workspace pages use.
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [history, datasets, saved, overview] = await Promise.all([
          api.get("/api/queries/history?limit=200"),
          api.get("/api/datasets"),
          api.get("/api/saved"),
          api.get("/api/realtime/overview")
        ]);
        if (!mounted) return;
        setStats({
          completed: (history || []).filter(h => h.status === "completed").length,
          datasets: (datasets || []).length,
          saved: (saved || []).length,
          live: (overview?.earthquakes?.events?.length || 0) + (overview?.weather?.cities?.length || 0),
          recent: (history || []).slice(0, 5)
        });
      } catch {
        if (mounted) setStats({ completed: 0, datasets: 0, saved: 0, live: 0, recent: [] });
      }
    })();
    return () => { mounted = false; };
  }, []);

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
      <div className="mt-0.5 truncate text-sm font-medium text-slate-200">{value || <span className="text-slate-600">â€”</span>}</div>
    </div>
  );

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
return (
    <div className="mx-auto max-w-6xl space-y-5">
      {/* Hero banner */}
      <section
        className="animate-fade-up relative overflow-hidden rounded-[28px] border border-hairline p-6 sm:p-8"
        style={{
          background:
            "linear-gradient(135deg, var(--fill-hover), transparent 55%), radial-gradient(600px 240px at 85% -20%, rgb(var(--c-accent) / 0.14), transparent 65%)"
        }}
      >
        <div aria-hidden="true" className="pointer-events-none absolute -left-10 top-0 h-40 w-40 rounded-full bg-accent/[0.08] blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-16 right-16 h-48 w-48 rounded-full bg-indigo-500/10 blur-3xl" />

        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="section-kicker !mb-0">Natural-language satellite intelligence</span>
              <span className="chip text-[10px] !text-slate-500">
                <CalendarDays className="mr-1 inline h-3 w-3" />
                {today}
              </span>
            </div>
            <h1 className="mt-2.5 text-[26px] font-semibold tracking-tight sm:text-[32px]">
              Welcome back, <span className="gradient-text">{user?.name?.split(" ")[0] || "analyst"}</span> ðŸ‘‹
            </h1>
            <p className="mt-1.5 max-w-xl text-[13px] leading-5 text-slate-500">
              Ask anything about the Earth in plain English â€” floods, crops, change,
              live earthquakes or weather. Your agents handle the rest.
            </p>
          </div>
          <div className="hidden shrink-0 items-center gap-2 sm:flex">
            <Link to="/results" className="btn-ghost !rounded-lg !py-1.5 !text-xs">
              <FileSearch className="h-3.5 w-3.5" /> My analyses
            </Link>
            <Link to="/history" className="btn-ghost !rounded-lg !py-1.5 !text-xs">
              <Clock className="h-3.5 w-3.5" /> History
            </Link>
          </div>
        </div>

        {/* Quick stats strip inside the hero */}
        <div className="relative mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {[
            ["11+", "datasets", Database, "text-accent"],
            ["4", "agents", Zap, "text-violet-400"],
            ["24/7", "live feeds", Radio, "text-rose-400"],
            ["2 min", "cache", Clock, "text-emerald-400"]
          ].map(([v, l, Icon, accent]) => (
            <div key={l} className="flex items-center gap-2.5 rounded-xl border border-hairline bg-space-900/50 px-3 py-2.5 backdrop-blur">
              <Icon className={`h-4 w-4 shrink-0 ${accent}`} />
              <div className="min-w-0">
                <div className="text-sm font-bold leading-tight tracking-tight">{v}</div>
                <div className="truncate text-[10px] uppercase tracking-wide text-slate-500">{l}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Stat cards */}
      <div className="grid animate-fade-up grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4" style={{ animationDelay: "0.05s" }}>
        <StatCard label="Completed analyses" value={stats ? String(stats.completed) : "â€“"} sub="in your workspace" icon={<Layers className="h-4 w-4" />} accent="text-accent" />
        <StatCard label="Datasets" value={stats ? String(stats.datasets) : "â€“"} sub="demo + live catalogue" icon={<Database className="h-4 w-4" />} accent="text-emerald-400" />
        <StatCard label="Live feeds" value={stats ? String(stats.live) : "â€“"} sub="earthquakes + weather" icon={<Radio className="h-4 w-4" />} accent="text-rose-400" />
        <StatCard label="Saved analyses" value={stats ? String(stats.saved) : "â€“"} sub="pinned reports" icon={<FolderHeart className="h-4 w-4" />} accent="text-violet-400" />
      </div>

      {/* Query composer */}
      <form
        onSubmit={submit}
        className="card animate-fade-up !p-5 transition focus-within:border-accent/40 focus-within:shadow-ambient-lg sm:!p-6"
        style={{ animationDelay: "0.1s" }}
      >
        <div className="relative">
          <span className="pointer-events-none absolute left-4 top-4 flex h-8 w-8 items-center justify-center rounded-[10px] bg-accent/10 text-accent">
            <Sparkles className="h-4 w-4" />
          </span>
          <textarea
            rows={3}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder='Try: "Show flood affected areas in Kerala in August 2024 using SAR data"'
            className="input !pl-14 !py-3.5 resize-none"
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e); }}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <kbd className="kbd">Ctrl</kbd>
            <span aria-hidden="true">+</span>
            <kbd className="kbd">â†µ</kbd>
            <span className="ml-1 hidden sm:inline">to run</span>
          </span>
          <Button type="submit" loading={running} className="!px-5">
            {running ? "Analyzingâ€¦" : "Run analysis"}
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
            {sure("Date range", understanding.date_start ? `${understanding.date_start} â†’ ${understanding.date_end}` : "Most recent")}
            {sure("Phenomenon", understanding.phenomenon)}
            {sure("Data type", understanding.data_type)}
            {sure("Analysis", understanding.requested_analysis)}
            {sure("Agent", understanding.agent)}
          </div>
        </Card>
      )}
      {/* Quick actions + notifications */}
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="card animate-fade-up !p-5" style={{ animationDelay: "0.15s" }}>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-accent">
            <Zap className="h-4 w-4" /> Quick actions
          </div>
          <div className="space-y-2">
            {QUICK_ACTIONS.map(a => {
              const Icon = a.icon;
              return (
                <Link
                  key={a.to}
                  to={a.to}
                  className={`group flex items-center gap-3 rounded-xl border border-hairline-strong bg-gradient-to-r ${a.ring} px-3.5 py-3 transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-ambient`}
                >
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-space-800/60 ${a.accent}`}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-semibold tracking-tight">{a.label}</span>
                    <span className="block truncate text-[11px] text-slate-500">{a.hint}</span>
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-accent" />
                </Link>
              );
            })}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            {[["Live", "data feeds"], ["11+", "datasets"], ["4", "agents"]].map(([v, l]) => (
              <div key={l} className="rounded-xl border border-space-700 bg-space-850/40 px-2 py-2.5">
                <div className="text-base font-bold text-accent">{v}</div>
                <div className="text-[10px] uppercase tracking-wide text-slate-500">{l}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Notifications */}
        <div className="card animate-fade-up !p-5" style={{ animationDelay: "0.2s" }}>
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-accent">
              <Bell className="h-4 w-4" /> Notifications
            </div>
            <button
              type="button"
              onClick={markAllRead}
              className="text-[11px] font-semibold text-accent transition hover:text-accent-soft"
            >
              Mark all read
            </button>
          </div>
          {notifications.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">No notifications â€” youâ€™re all caught up.</p>
          ) : (
            <ul className="space-y-1.5">
              {notifications.slice(0, 5).map(n => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (n.unread) markRead(n.id);
                      if (n.to) navigate(n.to);
                    }}
                    className="flex w-full items-start gap-3 rounded-xl border border-hairline bg-fill-quaternary px-3 py-2.5 text-left transition hover:border-accent/40 hover:bg-fill-hover"
                  >
                    <span
                      className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                        n.type === "success"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : n.type === "warn"
                          ? "bg-amber-500/10 text-amber-400"
                          : "bg-accent/10 text-accent"
                      }`}
                    >
                      {n.type === "success" ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : n.type === "warn" ? (
                        <Activity className="h-3.5 w-3.5" />
                      ) : (
                        <Bell className="h-3.5 w-3.5" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-[13px] font-semibold tracking-tight">{n.title}</span>
                        {n.unread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
                      </span>
                      <span className="block truncate text-xs text-slate-500">{n.message}</span>
                    </span>
                    <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-slate-600">{n.time}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Try an example */}
      <div className="card animate-fade-up !p-5" style={{ animationDelay: "0.25s" }}>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-accent">
          <LineChart className="h-4 w-4" /> Try an example
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {EXAMPLES.map((ex, i) => (
            <button
              key={ex}
              onClick={() => run(ex)}
              disabled={running}
              className="group flex items-start justify-between gap-2 rounded-xl border border-hairline-strong bg-space-850/40 px-3 py-2.5 text-left text-[13px] leading-5 text-slate-500 transition hover:-translate-y-0.5 hover:border-accent/50 hover:bg-space-850 hover:shadow-ambient hover:text-ink disabled:opacity-60"
            >
              <span className="min-w-0">
                <span className="mr-1.5 font-mono text-[11px] text-slate-600 transition group-hover:text-accent">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {ex}
              </span>
              <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600 transition group-hover:text-accent" />
            </button>
          ))}
        </div>
      </div>

      {running && (
        <div className="card flex items-center gap-3 px-5 py-4">
          <Spinner className="h-5 w-5" />
          <div>
            <div className="text-sm font-medium text-slate-200">Running satellite pipelineâ€¦</div>
            <div className="text-xs text-slate-500">Understanding â†’ agent â†’ retrieval â†’ processing â†’ verification</div>
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
