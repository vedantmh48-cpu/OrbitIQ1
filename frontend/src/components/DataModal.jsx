import { useEffect, useState } from "react";
import { X, Activity, MapPin, ArrowRight, ExternalLink, Droplet, Wind, Thermometer, Waves } from "lucide-react";
import { api, formatNumber } from "../api/client.js";
import { Badge, SimulatedBadge, Spinner } from "./ui.jsx";
import MapView from "./MapView.jsx";
import { LineChart as ReLine, Line, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const OP_COLORS = {
  "flood-mapping": "#0ea5e9", "change-detection": "#f97316",
  "classification": "#22c55e", "object-detection": "#eab308",
  "time-series": "#a855f7", "fusion": "#8b5cf6", "terrain": "#a8a29e",
  "image-search": "#38bdf8", "real-events": "#f43f5e"
};

export default function DataModal({ kind, data, onClose, onAnalyze }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (kind === "dataset" && data?.id) {
      setLoading(true);
      api.get(`/api/datasets/${data.id}`)
        .then(d => { setDetail(d); setLoading(false); })
        .catch(e => { setError(e.message); setLoading(false); });
    }
  }, [kind, data]);

  if (!data) return null;
  const obj = detail || data;
  const simulated = obj.simulated ?? false;
  const opColor = OP_COLORS[obj.op] || "#0ea5e9";
  const preview = obj.preview || obj.geojson || obj.geojson_preview;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="card relative my-8 w-full max-w-3xl !bg-space-900" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-space-700 px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-bold text-white">{obj.name || obj.label || obj.title || "Details"}</h2>
              {simulated ? <SimulatedBadge simulated /> : <Badge color="green">Live</Badge>}
              {obj.data_type && <Badge color="slate">{obj.data_type}</Badge>}
              {obj.op && <span className="chip" style={{ borderColor: `${opColor}66`, color: opColor }}>{obj.op}</span>}
            </div>
            <p className="mt-1 max-w-xl text-sm text-slate-400">{obj.description || obj.place || obj.city || "—"}</p>
          </div>
          <button onClick={onClose} className="rounded p-1.5 text-slate-400 hover:bg-space-800 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-5 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-12"><Spinner label="Loading details…" /></div>
          ) : error ? (
            <p className="text-sm text-rose-400">{error}</p>
          ) : (
            <>
              {preview && (
                <div>
                  <div className="mb-2 text-sm font-semibold text-slate-200">Map preview</div>
                  <div className="h-64 overflow-hidden rounded-lg">
                    <MapView geojson={preview} op={obj.op || "real-events"} baseLayer="Dark" />
                  </div>
                </div>
              )}
              <FactTiles obj={obj} />
              {(kind === "dataset" || obj.satellite || obj.tags) && <MetaGrid obj={obj} />}
              {(obj.series || obj.hourly) && <SeriesCard series={obj.series || obj.hourly} />}
              <div className="flex flex-wrap items-center gap-2 border-t border-space-700 pt-4">
                {onAnalyze && (
                  <button className="btn-primary" onClick={() => onAnalyze(obj)}>
                    Run analysis for this area <ArrowRight className="h-4 w-4" />
                  </button>
                )}
                {kind === "quickview" && obj.result_id && (
                  <a className="btn-ghost" href={`/results/${obj.result_id}`}>
                    Open full result <ExternalLink className="h-4 w-4" />
                  </a>
                )}
                {obj.license && <span className="ml-auto text-xs text-slate-500">{obj.license}</span>}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
function FactTiles({ obj }) {
  const tiles = [];
  if (obj.mag != null) tiles.push({ icon: <Activity className="h-4 w-4" />, label: "Magnitude", value: Number(obj.mag).toFixed(1) });
  if (obj.depth_km != null) tiles.push({ icon: <Waves className="h-4 w-4" />, label: "Depth", value: `${obj.depth_km} km` });
  if (obj.temperature_c != null) tiles.push({ icon: <Thermometer className="h-4 w-4" />, label: "Temperature", value: `${Math.round(obj.temperature_c)}°C` });
  if (obj.relative_humidity != null) tiles.push({ icon: <Droplet className="h-4 w-4" />, label: "Humidity", value: `${obj.relative_humidity}%` });
  if (obj.wind_speed_kmh != null) tiles.push({ icon: <Wind className="h-4 w-4" />, label: "Wind", value: `${Math.round(obj.wind_speed_kmh)} km/h` });
  if (obj.cloud_cover != null) tiles.push({ icon: <Droplet className="h-4 w-4" />, label: "Clouds", value: `${obj.cloud_cover}%` });
  if (obj.pressure_hpa != null) tiles.push({ icon: <Activity className="h-4 w-4" />, label: "Pressure", value: `${Math.round(obj.pressure_hpa)} hPa` });
  if (obj.affected_area_km2 != null) tiles.push({ icon: <MapPin className="h-4 w-4" />, label: "Area", value: `${formatNumber(obj.affected_area_km2)} km²` });
  if (!tiles.length) return null;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {tiles.map(t => (
        <div key={t.label} className="rounded-lg border border-space-700 bg-space-850/60 px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <span className="text-accent">{t.icon}</span> {t.label}
          </div>
          <div className="mt-0.5 text-lg font-bold text-white">{t.value}</div>
        </div>
      ))}
    </div>
  );
}

function MetaGrid({ obj }) {
  const rows = [
    ["Satellite / source", obj.satellite || obj.source],
    ["Resolution", obj.resolution],
    ["Temporal range", obj.temporal?.start && obj.temporal?.end ? `${obj.temporal.start.slice(0, 10)} → ${obj.temporal.end.slice(0, 10)}` : undefined],
    ["Provider", obj.provider_label || obj.provider_id],
    ["Observed at", obj.observed_at?.replace("T", " ").slice(0, 19)],
    ["License", obj.license]
  ].filter(([, v]) => v);
  return (
    <div>
      <div className="mb-2 text-sm font-semibold text-slate-200">Dataset metadata</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{k}</div>
            <div className="text-slate-300">{v}</div>
          </div>
        ))}
      </div>
      {obj.tags?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {obj.tags.map(t => <span key={t} className="chip !text-[10px]">{t}</span>)}
        </div>
      )}
      <p className="mt-3 truncate text-xs text-slate-500">{obj.description}</p>
    </div>
  );
}

function SeriesCard({ series }) {
  const rows = series.slice(-60).map(s => ({
    name: (s.time || s.date || "").slice(0, 10),
    value: s.temperature_c ?? s.value ?? s.precipitation_mm
  })).filter(s => s.value != null);
  if (!rows.length) return null;
  return (
    <div>
      <div className="mb-2 text-sm font-semibold text-slate-200">Series</div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <ReLine data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 10 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
            <RTooltip contentStyle={{ background: "#0d1729", border: "1px solid #243a61", borderRadius: 8 }} />
            <Line type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2} dot={false} />
          </ReLine>
        </ResponsiveContainer>
      </div>
    </div>
  );
}