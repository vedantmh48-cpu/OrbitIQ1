import { useEffect, useState } from "react";
import { Database, Radar, Satellite, Mountain, Table2, Map as MapIcon, LineChart, Search as SearchIcon, ChevronRight, Radio } from "lucide-react";
import { api } from "../api/client.js";
import { Alert, Badge, Card, SimulatedBadge, Skeleton } from "../components/ui.jsx";
import DataModal from "../components/DataModal.jsx";

const TYPE_ICONS = {
  SAR: Radar, Optical: Satellite, DEM: Mountain,
  Vector: MapIcon, "Time-Series": LineChart, Tabular: Table2, Fusion: Database
};

const TYPE_COLORS = {
  SAR: "#38bdf8", Optical: "#4ade80", DEM: "#a8a29e", Vector: "#fb923c",
  "Time-Series": "#a855f7", Tabular: "#f59e0b", Fusion: "#c084fc"
};

export default function Datasets() {
  const [datasets, setDatasets] = useState(null);
  const [providers, setProviders] = useState([]);
  const [feeds, setFeeds] = useState([]);
  const [type, setFilterType] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (type) params.set("data_type", type);
      if (q) params.set("q", q);
      setDatasets(await api.get(`/api/datasets?${params}`));
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    (async () => {
      load();
      try {
        setProviders(await api.get("/api/datasets/providers"));
      } catch { /* optional */ }
      try {
        const rt = await api.get("/api/realtime/datasets");
        setFeeds(rt.feeds || []);
      } catch { /* realtime feeds optional */ }
    })();
  }, [type, q]);

  const fullList = [...feeds, ...(datasets || [])];
  const analyze = obj => {
    setDetail(null);
    const qtext =
      obj.id && (obj.id.includes("earthquake") || obj.id.includes("weather"))
        ? obj.id.includes("earthquake")
          ? `Show recent earthquakes${obj.location?.name ? ` in ${obj.location.name}` : ""}`
          : `What is the current weather in ${(obj.tags || []).includes("global") ? "Mumbai" : (obj.location?.name || "Mumbai")}`
        : `Analyse ${obj.name || "this dataset"} in ${(obj.location?.name) || "this area"} using ${obj.data_type || "the best"} data`;
    window.location.href = `/dashboard?q=${encodeURIComponent(qtext)}`;
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Data catalogue</h1>
        <p className="mt-1 text-sm text-slate-400">Available datasets across all provider adapters — demo data is clearly labelled.</p>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {/* provider status */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {providers.map(p => (
          <div key={p.id} className="card flex items-center justify-between px-4 py-3 text-sm">
            <span className="font-medium text-slate-200">{p.label}</span>
            <Badge color={p.available ? "green" : "slate"}>{p.available ? "Available" : "Not configured"}</Badge>
          </div>
        ))}
      </div>

      {/* filters */}
      <Card className="!p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <SearchIcon className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input className="input !pl-9" placeholder="Search datasets…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <select className="input !w-auto" value={type} onChange={e => setType(e.target.value)}>
            <option value="">All data types</option>
            {Object.keys(TYPE_COLORS).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </Card>

      {/* live catalogue */}
      {feeds.length > 0 && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-accent">
            <Radio className="h-4 w-4" /> Live feeds (real-time)
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {feeds.map(d => <DatasetCard key={d.id} d={d} onOpen={setDetail} />)}
          </div>
        </div>
      )}

      {/* catalog */}
      {!datasets ? (
        <div className="grid gap-3 md:grid-cols-2">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32 rounded-xl" />)}
        </div>
      ) : (
        <div>
          {datasets.length > 0 && (
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
              All datasets · click a card for full details
            </h2>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            {datasets.map(d => <DatasetCard key={d.id} d={d} onOpen={setDetail} />)}
            {datasets.length === 0 && (
              <Card className="py-10 text-center text-sm text-slate-500">No datasets match your filters.</Card>
            )}
          </div>
        </div>
      )}

      {detail && (
        <DataModal kind="dataset" data={detail} onClose={() => setDetail(null)} onAnalyze={analyze} />
      )}
    </div>
  );
}

function DatasetCard({ d, onOpen }) {
  const Icon = TYPE_ICONS[d.data_type] || Database;
  const color = TYPE_COLORS[d.data_type] || "#38bdf8";
  return (
    <button
      onClick={() => onOpen(d)}
      className="card group p-4 text-left transition hover:border-accent/50 hover:shadow-lg hover:shadow-accent/5"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-lg p-2" style={{ background: `${color}1a`, color }}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-100">{d.name}</span>
            {d.simulated ? <SimulatedBadge simulated /> : <Badge color="green">Live</Badge>}
          </div>
          <p className="mt-1 truncate text-xs text-slate-500">{d.description}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <Badge color="slate">{d.data_type}</Badge>
            <span>{d.satellite}</span>
            <span>· {d.resolution}</span>
            {d.temporal?.start && d.temporal?.end && (
              <span>· {d.temporal.start.slice(0, 4)}–{d.temporal.end.slice(0, 4)}</span>
            )}
          </div>
        </div>
        <ChevronRight className="mt-2 h-5 w-5 shrink-0 text-slate-600 transition group-hover:text-accent" />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-space-800 pt-2.5">
        {(d.tags || []).slice(0, 6).map(t => <span key={t} className="chip !text-[10px]">{t}</span>)}
        {d.source && <span className="ml-auto text-[10px] uppercase tracking-wide text-slate-600">{d.source}</span>}
      </div>
    </button>
  );
}