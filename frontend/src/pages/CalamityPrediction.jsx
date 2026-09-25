import { useEffect, useState } from "react";
import {
  ShieldAlert, Activity, Tornado, Flame, Waves, CloudLightning,
  ThermometerSun, RefreshCw, MapPin, Radio, AlertOctagon, Satellite,
  Navigation, Search as SearchIcon, X
} from "lucide-react";
import { api } from "../api/client.js";
import { Alert, Badge, SectionTitle } from "../components/ui.jsx";

const HAZARD_ICON = {
  earthquake: Activity,
  flood: Waves,
  storm: Tornado,
  heatwave: ThermometerSun,
  wildfire: Flame,
  thunderstorm: CloudLightning
};

const HAZARD_COLOR = {
  earthquake: "#f43f5e",
  flood: "#38bdf8",
  storm: "#a855f7",
  heatwave: "#fb923c",
  wildfire: "#f97316",
  thunderstorm: "#eab308"
};

const LEVEL_HEX = {
  Low: "#34d399",
  Moderate: "#fbbf24",
  High: "#fb923c",
  Extreme: "#f43f5e"
};

const LEVEL_STYLE = {
  Low: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
  Moderate: "border-amber-500/40 text-amber-400 bg-amber-500/10",
  High: "border-orange-500/40 text-orange-400 bg-orange-500/10",
  Extreme: "border-rose-500/40 text-rose-400 bg-rose-500/10"
};

const CONF_COLOR = { Low: "slate", Medium: "amber", High: "green" };

function scoreColor(score) {
  if (score >= 75) return LEVEL_HEX.Extreme;
  if (score >= 50) return LEVEL_HEX.High;
  if (score >= 25) return LEVEL_HEX.Moderate;
  return LEVEL_HEX.Low;
}

export default function CalamityPrediction() {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState("");
  const [custom, setCustom] = useState(null); // { name, latitude, longitude }
  const [search, setSearch] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const predictionsUrl = target => {
    const t = target || custom;
    if (t && t.latitude != null && t.longitude != null) {
      return `/api/realtime/predictions?lat=${t.latitude}&lng=${t.longitude}&name=${encodeURIComponent(t.name || "My location")}`;
    }
    return "/api/realtime/predictions";
  };

  const load = async (showSpinner = false, target = null) => {
    if (showSpinner) setRefreshing(true);
    try {
      const res = await api.get(predictionsUrl(target));
      setData(res);
      if (res.cities?.length) setSelected(res.cities[0].city);
    } catch (e) {
      setError(e.message);
      if (!data) setData({ cities: [], alerts: [] });
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  };

  const selectPreset = city => {
    setCustom(null);
    setSelected(city);
    load(false, null);
  };

  const selectCustom = place => {
    const target = {
      name: place.label || place.name || "My location",
      latitude: place.latitude,
      longitude: place.longitude
    };
    setCustom(target);
    setSelected(target.name);
    setSearch("");
    setSuggestions([]);
    load(true, target);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setError("Device location is not available in this browser. Search for a city instead.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      pos => selectCustom({ name: "My location", latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => setError("Could not access your device location. Search for a city instead.")
    );
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const t = setInterval(() => load(false), 300000);
    return () => clearInterval(t);
  }, [custom]);

  // Debounced place-name -> coordinates search (Open-Meteo geocoding).
  useEffect(() => {
    const q = search.trim();
    if (q.length < 2) {
      setSuggestions([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.get(`/api/realtime/geocode?q=${encodeURIComponent(q)}&limit=5`);
        setSuggestions(res.results || []);
      } catch {
        setSuggestions([]);
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  if (!data) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="section-kicker">Early-warning risk engine</div>
        <h1 className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Natural Calamity Prediction
        </h1>
        {error && <Alert type="error">{error}</Alert>}
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card animate-pulse p-8">
              <div className="h-6 w-40 rounded bg-space-800/70" />
              <div className="mt-4 h-24 rounded-lg bg-space-800/70" />
              <div className="mt-3 h-10 rounded bg-space-800/70" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const cities = (data.cities || []).filter(c => c.city);
  const city = cities.find(c => c.city === selected) || cities[0] || null;
  const alerts = data.alerts || [];
  const updated = (data.updated_at || "").replace("T", " ").slice(0, 19);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="animate-fade-up">
        <div className="section-kicker">Early-warning risk engine · {data.source || "USGS + Open-Meteo"}</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Natural Calamity Prediction Engine
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          A transparent statistical model over genuinely live feeds — USGS seismic
          events and the Open-Meteo 7-day forecast — scoring the near-term risk of
          earthquakes, floods, cyclones, heatwaves, wildfires and thunderstorms for
          <span className="font-semibold text-accent">any location you choose</span>.
          Each hazard is rated Low → Extreme with the signals that drive it.
        </p>
      </div>

      {error && <Alert type="error">{error}</Alert>}
      {data.real === false && (
        <Alert type="warn">Live feeds are currently cached — predictions reflect the last successful refresh.</Alert>
      )}

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip !cursor-default">
          <Radio className="mr-1 h-3.5 w-3.5 text-accent" /> Model run {updated} UTC
        </span>
        <button onClick={() => load(true)} className="chip !cursor-pointer hover:border-accent hover:text-accent">
          <RefreshCw className="mr-1 h-3.5 w-3.5" /> {refreshing ? "Refreshing…" : "Rerun"}
        </button>
      </div>

      {/* regional watchlist */}
      {alerts.length > 0 && (
        <div className="card border-l-4 !border-l-rose-500/60 p-5">
          <SectionTitle icon={<AlertOctagon className="h-4 w-4 text-rose-400" />}>
            Regional watchlist · High or Extreme risk in the next 7 days
          </SectionTitle>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {alerts.map(a => (
              <div key={`${a.city}-${a.hazard}`} className="rounded-xl border border-rose-500/30 bg-rose-500/5 px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-100">
                    <MapPin className="mr-1 h-3.5 w-3.5 text-accent" />{a.city}
                  </span>
                  <Badge color="red">{a.level} · {a.score}</Badge>
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {a.hazard} — {a.confidence} confidence
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* change location */}
      <div className="relative">
        <label className="label" htmlFor="prediction-location-search">Change location</label>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            id="prediction-location-search"
            className="input !pl-9"
            placeholder="Search any city or town… (e.g. Bengaluru, Sydney, Kathmandu)"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {searching && (
            <span className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
          )}
        </div>
        {suggestions.length > 0 && (
          <div className="absolute left-0 right-0 z-30 mt-1 max-h-72 overflow-y-auto rounded-2xl border border-space-700 bg-space-900/95 shadow-2xl backdrop-blur-md">
            {suggestions.map(r => (
              <button
                key={`${r.name}-${r.latitude}-${r.longitude}`}
                onClick={() => selectCustom(r)}
                className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left text-sm text-slate-200 transition hover:bg-space-800 hover:text-white"
              >
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.name}</span>
                  <span className="block truncate text-[11px] text-slate-500">
                    {r.label} · {Number(r.latitude).toFixed(2)}°, {Number(r.longitude).toFixed(2)}°
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-500">
          <button type="button" onClick={useMyLocation} className="chip !cursor-pointer hover:border-accent hover:text-accent">
            <Navigation className="mr-1 h-3 w-3" /> Use my location
          </button>
          {custom && (
            <span className="chip !cursor-default">
              Modelling <span className="font-semibold text-accent">{custom.name}</span>
              <button type="button" title="Back to global cities" onClick={() => selectPreset(cities[0]?.city || "")} className="ml-1 align-middle">
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
        </div>
      </div>

      {/* city selector */}
      {!custom ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">City:</span>
          {cities.map(c => (
            <button
              key={c.city}
              onClick={() => selectPreset(c.city)}
              className={`chip !cursor-pointer ${c.city === city?.city ? "!border-accent/60 !text-accent" : ""}`}
            >
              <MapPin className="mr-1 h-3.5 w-3.5" />
              {c.city}
              {c.overall_level === "High" && <span className="ml-1 text-orange-400">▲</span>}
              {c.overall_level === "Extreme" && <span className="ml-1 text-rose-400">▲▲</span>}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip !cursor-default">
            <MapPin className="mr-1 h-3.5 w-3.5 text-accent" />
            <span className="font-semibold text-accent">{city?.city || custom.name}</span>
          </span>
          <span className="text-[11px] text-slate-500">
            {Number(city?.lat || custom.latitude).toFixed(2)}°, {Number(city?.lng || custom.longitude).toFixed(2)}°
            · risk scored at these exact coordinates (real USGS + Open-Meteo data)
          </span>
        </div>
      )}

      {!city ? (
        <Alert type="warn">No predictions available right now. Check your connection and try again.</Alert>
      ) : (
        <>
          <CityOverview city={city} />
          <HazardGrid city={city} />
        </>
      )}

      <div className="card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-accent">
          <Satellite className="h-4 w-4" /> Methodology & data
        </div>
        <p className="text-xs leading-5 text-slate-500">{data.methodology}</p>
      </div>
    </div>
  );
}

function GaugeRing({ score, size = 160 }) {
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  const color = scoreColor(value);
  const r = 64, c = 2 * Math.PI * r;
  const offset = c * (1 - value / 100);
  return (
    <svg width={size} height={size} viewBox="0 0 160 160" className="shrink-0" role="img" aria-label={`Risk score ${value} out of 100`}>
      <circle cx="80" cy="80" r={r} fill="none" stroke="#1e293b" strokeWidth="13" />
      <circle
        cx="80" cy="80" r={r} fill="none" stroke={color} strokeWidth="13"
        strokeLinecap="round" strokeDasharray={`${c} ${c}`} strokeDashoffset={offset}
        transform="rotate(-90 80 80)"
      />
      <text x="80" y="76" textAnchor="middle" fontSize="30" fontWeight="800" fill="#e6edf7">
        {Math.round(value)}
      </text>
      <text x="80" y="102" textAnchor="middle" fontSize="13" fill="#64748b">of 100</text>
    </svg>
  );
}

function CityOverview({ city }) {
  const top = city.max_hazard || {};
  return (
    <div className="card p-6">
      <SectionTitle icon={<ShieldAlert className="h-4 w-4" />}>
        Risk profile · <span className="text-slate-300">{city.city}</span>
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-6">
        <GaugeRing score={city.max_score} />
        <div className="min-w-0 flex-1">
          <div className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${LEVEL_STYLE[city.overall_level] || LEVEL_STYLE.Low}`}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: LEVEL_HEX[city.overall_level] || LEVEL_HEX.Low }} />
            Overall risk — {city.overall_level}
          </div>
          {top.label && (
            <p className="mt-2 text-sm text-slate-300">
              Leading concern: <span className="font-semibold text-white">{top.label}</span>
              {top.confidence && <span className="text-slate-500"> · {top.confidence.toLowerCase()} confidence</span>}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {["Low <25", "Moderate 25–49", "High 50–74", "Extreme ≥75"].map(scale => (
              <span key={scale} className="chip !text-[10px]">{scale}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function HazardCard({ hazard }) {
  const Icon = HAZARD_ICON[hazard.id] || ShieldAlert;
  const color = HAZARD_COLOR[hazard.id] || "#22d3ee";
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2.5">
        <div className="rounded-lg p-2" style={{ background: `${color}1a`, color }}>
          <Icon className="h-5 w-5" />
        </div>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-100">{hazard.label}</span>
        <Badge color={CONF_COLOR[hazard.confidence] || "slate"}>
          {hazard.confidence} confidence
        </Badge>
      </div>

      {/* score bar */}
      <div className="mt-3 flex items-center gap-2">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-space-800">
          <div
            className="h-2 rounded-full transition-all"
            style={{ width: `${Math.max(2, hazard.score)}%`, background: scoreColor(hazard.score) }}
          />
        </div>
        <span
          className="w-14 text-right font-mono text-sm font-bold"
          style={{ color: scoreColor(hazard.score) }}
        >
          {hazard.score}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-xs">
        <span className={`rounded-full border px-2 py-0.5 ${LEVEL_STYLE[hazard.level] || LEVEL_STYLE.Low}`}>
          {hazard.level}
        </span>
      </div>

      {/* indicators */}
      {hazard.indicators?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {hazard.indicators.map((ind, i) => (
            <span key={i} className="chip !text-[10px]" title={ind.label}>
              {ind.label}: {ind.value}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2.5 border-t border-space-800 pt-2 text-xs leading-5 text-slate-400">
        <span className="text-accent">Recommended — </span>{hazard.recommendation}
      </div>
    </div>
  );
}

function HazardGrid({ city }) {
  if (!city.hazards?.length) return null;
  return (
    <div className="space-y-1">
      <SectionTitle icon={<Flame className="h-4 w-4 text-rose-400" />}>
        Hazard-by-hazard forecast · 7 days
      </SectionTitle>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {city.hazards.map(h => <HazardCard key={h.id} hazard={h} />)}
      </div>
    </div>
  );
}