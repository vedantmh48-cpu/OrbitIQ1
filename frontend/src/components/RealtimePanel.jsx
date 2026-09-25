import { useEffect, useState } from "react";
import { Activity, CloudSun, Radio } from "lucide-react";
import { api } from "../api/client.js";
import { Alert, Badge } from "./ui.jsx";
import DataModal from "./DataModal.jsx";

const WEATHER_CODES = {
  0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
  45: "Fog", 48: "Rime fog", 51: "Drizzle", 61: "Rain (light)",
  63: "Rain (moderate)", 65: "Rain (heavy)", 71: "Snow", 80: "Rain showers",
  95: "Thunderstorm"
};

function weatherLabel(code) {
  if (code === null || code === undefined) return "—";
  return WEATHER_CODES[Number(code)] || `Code ${code}`;
}

export default function RealtimePanel() {
  const [overview, setOverview] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      setOverview(await api.get("/api/realtime/overview"));
    } catch (e) {
      setError(e.message);
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const t = setInterval(() => load(), 90000);
    return () => clearInterval(t);
  }, []);

  if (!overview) {
    return (
      <div className="card animate-pulse p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-accent">
          <Radio className="h-4 w-4 animate-pulse-slow" /> Live observations
        </div>
        <div className="space-y-3">
          <div className="h-20 rounded-lg bg-space-800/60" />
          <div className="h-20 rounded-lg bg-space-800/60" />
        </div>
      </div>
    );
  }

  const quakes = (overview.earthquakes?.events || []).slice(0, 6);
  const cities = (overview.weather?.cities || []).slice(0, 6);
  const updated = (overview.updated_at || "").replace("T", " ").slice(0, 19);

  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-accent">
          <Radio className="h-4 w-4" /> Live observations
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-1.5 text-xs text-slate-500 sm:flex">
            <span className="h-1.5 w-1.5 animate-pulse-slow rounded-full bg-emerald-400" />
            {overview.real ? "Real-time · " : "Cached · "} updated {updated}
          </span>
          <button onClick={() => load(true)} className="chip !cursor-pointer hover:border-accent hover:text-accent">
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <div className="mb-3"><Alert type="warn">{error}</Alert></div>}

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Activity className="mr-1 inline h-3.5 w-3.5 text-rose-400" /> Earthquakes · last 48h
            </span>
            <Badge color="slate">{overview.earthquakes?.events?.length || 0} events</Badge>
          </div>
          <div className="space-y-2">
            {quakes.length === 0 && <p className="text-sm text-slate-600">No recent events above threshold.</p>}
            {quakes.map(ev => (
              <button
                key={ev.id}
                onClick={() => setSelected({ kind: "event", data: { ...ev, source: "USGS Earthquake Hazards Program" } })}
                className="w-full rounded-lg border border-space-700 bg-space-850/60 px-3 py-2 text-left transition hover:border-rose-500/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`truncate text-sm font-medium ${ev.mag >= 5 ? "text-amber-300" : "text-slate-200"}`}>
                    M {ev.mag != null ? Number(ev.mag).toFixed(1) : "?"} — {ev.place || "Unknown"}
                  </span>
                  <span className="shrink-0 text-[11px] text-slate-500">{ev.depth_km} km</span>
                </div>
                {ev.time && (
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    {new Date(ev.time).toUTCString().slice(0, 17)}
                    {ev.tsunami && <span className="ml-2 text-rose-400">⚠ tsunami alert</span>}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              <CloudSun className="mr-1 inline h-3.5 w-3.5 text-accent" /> Weather · global cities
            </span>
            <Badge color="slate">{overview.weather?.cities?.length || 0} stations</Badge>
          </div>
          <div className="space-y-2">
            {cities.length === 0 && <p className="text-sm text-slate-600">Weather feed unavailable.</p>}
            {cities.map(c => (
              <button
                key={c.city}
                onClick={() => setSelected({ kind: "event", data: { ...c, source: "Open-Meteo (NOAA model)" } })}
                className="w-full rounded-lg border border-space-700 bg-space-850/60 px-3 py-2 text-left transition hover:border-accent/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-slate-200">{c.city}</span>
                  <span className="shrink-0 text-sm font-bold text-accent">
                    {c.temperature_c != null ? `${Math.round(c.temperature_c)}°C` : "—"}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-3 text-[11px] text-slate-500">
                  <span>{weatherLabel(c.weather_code)}</span>
                  <span>💧 {c.relative_humidity ?? "—"}%</span>
                  <span>💨 {c.wind_speed_kmh != null ? Math.round(c.wind_speed_kmh) : "—"}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-slate-600">
        Sources: USGS Earthquake Hazards Program · Open-Meteo (NOAA model). Click any card for full details.
      </p>

      {selected && (
        <DataModal
          kind="event"
          data={{ ...selected.data, real: true }}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}