import { useEffect, useState } from "react";
import {
  CloudSun, Cloudy, CloudFog, CloudRainWind, CloudLightning, CloudSnow,
  Droplets, Wind, Thermometer, Sun, Sunrise, Sunset, Eye, Gauge,
  RefreshCw, MapPin, Activity, Umbrella, Navigation,
  Search as SearchIcon, X
} from "lucide-react";
import {
  LineChart as ReLine, Line, XAxis, YAxis, Tooltip as RTooltip,
  ResponsiveContainer, CartesianGrid
} from "recharts";
import { api } from "../api/client.js";
import { Alert, SectionTitle } from "../components/ui.jsx";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const WEATHER_META = {
  0: { label: "Clear sky", icon: Sun },
  1: { label: "Mainly clear", icon: Sun },
  2: { label: "Partly cloudy", icon: CloudSun },
  3: { label: "Overcast", icon: Cloudy },
  45: { label: "Fog", icon: CloudFog },
  48: { label: "Rime fog", icon: CloudFog },
  51: { label: "Light drizzle", icon: Droplets },
  53: { label: "Drizzle", icon: Droplets },
  55: { label: "Dense drizzle", icon: Droplets },
  56: { label: "Freezing drizzle", icon: Droplets },
  57: { label: "Freezing drizzle", icon: Droplets },
  61: { label: "Light rain", icon: CloudRainWind },
  63: { label: "Rain", icon: CloudRainWind },
  65: { label: "Heavy rain", icon: CloudRainWind },
  66: { label: "Freezing rain", icon: CloudRainWind },
  67: { label: "Freezing rain", icon: CloudRainWind },
  71: { label: "Light snow", icon: CloudSnow },
  73: { label: "Snow", icon: CloudSnow },
  75: { label: "Heavy snow", icon: CloudSnow },
  80: { label: "Rain showers", icon: CloudRainWind },
  81: { label: "Rain showers", icon: CloudRainWind },
  82: { label: "Violent showers", icon: CloudRainWind },
  85: { label: "Snow showers", icon: CloudSnow },
  86: { label: "Snow showers", icon: CloudSnow },
  95: { label: "Thunderstorm", icon: CloudLightning },
  96: { label: "Thunderstorm with hail", icon: CloudLightning },
  99: { label: "Severe thunderstorm", icon: CloudLightning }
};

const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

function weatherMeta(code) {
  return WEATHER_META[Number(code)] || { label: `Code ${code}`, icon: Cloudy };
}

function compass(deg) {
  if (deg === null || deg === undefined) return "—";
  return COMPASS[Math.round((Number(deg) % 360) / 22.5) % 16];
}

function shortTime(iso) {
  if (!iso) return "—";
  const t = iso.length > 10 ? iso.slice(11, 16) : iso;
  try {
    const [h, m] = t.split(":");
    const hour = Number(h) % 12 || 12;
    return `${hour}:${(m || "00").padStart(2, "0")}${Number(h) < 12 ? "a" : "p"}`;
  } catch {
    return t;
  }
}

export default function WeatherForecast() {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState("");
  const [custom, setCustom] = useState(null); // { name, latitude, longitude } when a user-chosen location
  const [search, setSearch] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const forecastUrl = target => {
    const t = target || custom;
    if (t && t.latitude != null && t.longitude != null) {
      return `/api/realtime/forecast?lat=${t.latitude}&lng=${t.longitude}&name=${encodeURIComponent(t.name || "My location")}`;
    }
    return "/api/realtime/forecast";
  };

  const load = async (showSpinner = false, target = null) => {
    if (showSpinner) setRefreshing(true);
    try {
      const res = await api.get(forecastUrl(target));
      setData(res);
      if (res.cities?.length) setSelected(res.cities[0].city);
    } catch (e) {
      setError(e.message);
      if (!data) setData({ cities: [] });
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
        <div className="section-kicker">Real-time meteorology</div>
        <h1 className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Weather Forecast
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
  const updated = (data.observed_at || "").replace("T", " ").slice(0, 19);

  if (!city) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="section-kicker">Real-time meteorology</div>
        <h1 className="text-2xl font-extrabold tracking-tight text-white">Weather Forecast</h1>
        {error && <Alert type="error">{error}</Alert>}
        <Alert type="warn">No live forecast available right now. Check your connection and try again.</Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="animate-fade-up">
        <div className="section-kicker">Real-time meteorology · {data.source || "Open-Meteo"}</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          Weather Forecast
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Live current conditions plus hourly and 7-day outlook — for any location
          you choose. Search a city below or pick a quick-start city. Data is
          refreshed from Open-Meteo (NOAA/GFS model) every 5 minutes.
        </p>
      </div>

      {error && <Alert type="error">{error}</Alert>}
      {data.real === false && <Alert type="warn">Provider feed is currently cached — values are from the last successful refresh.</Alert>}

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip !cursor-default">
          <Activity className="mr-1 h-3.5 w-3.5 text-accent" /> Updated {updated} UTC
        </span>
        <button onClick={() => load(true)} className="chip !cursor-pointer hover:border-accent hover:text-accent">
          <RefreshCw className="mr-1 h-3.5 w-3.5" /> {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* change location */}
      <div className="relative">
        <label className="label" htmlFor="weather-location-search">Change location</label>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            id="weather-location-search"
            className="input !pl-9"
            placeholder="Search any city or town… (e.g. Bengaluru, Sydney, New York)"
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
              Showing <span className="font-semibold text-accent">{custom.name}</span>
              <button type="button" title="Back to global cities" onClick={() => selectPreset(cities[0]?.city || "")} className="ml-1 align-middle">
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
        </div>
      </div>

      {/* city selector */}
      {!custom && (
        <div className="flex flex-wrap gap-2">
          {cities.map(c => (
            <button
              key={c.city}
              onClick={() => selectPreset(c.city)}
              className={`chip !cursor-pointer ${c.city === city.city ? "!border-accent/60 !text-accent" : ""}`}
            >
              <MapPin className="mr-1 h-3.5 w-3.5" />
              {c.city}
            </button>
          ))}
        </div>
      )}
      {custom && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip !cursor-default">
            <MapPin className="mr-1 h-3.5 w-3.5 text-accent" />
            <span className="font-semibold text-accent">{city?.city || custom.name}</span>
          </span>
          <span className="text-[11px] text-slate-500">
            {Number(city?.lat || custom.latitude).toFixed(2)}°, {Number(city?.lng || custom.longitude).toFixed(2)}°
            · forecast fetched for these exact coordinates
          </span>
        </div>
      )}

      {city.error ? (
        <Alert type="warn">{city.city} — live data temporarily unavailable.</Alert>
      ) : (
        <>
          <CurrentConditions city={city} />
          <DailyForecast days={city.daily} />
          <HourlyForecast hours={city.hourly} />
          <p className="text-[11px] text-slate-600">
            Source: Open-Meteo (NOAA / GFS numerical weather model). All times UTC unless the
            city timezone differs; values are model forecasts as published by the provider.
          </p>
        </>
      )}
    </div>
  );
}

function StatBox({ icon, label, value }) {
  return (
    <div className="rounded-xl border border-space-700 bg-space-850/60 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {icon} {label}
      </div>
      <div className="mt-0.5 text-sm font-bold text-slate-100">{value || "—"}</div>
    </div>
  );
}

function CurrentConditions({ city }) {
  const cur = city.current || {};
  const meta = weatherMeta(cur.weather_code);
  const Icon = meta.icon;
  const today = (city.daily || [])[0] || {};
  return (
    <div className="card p-5">
      <SectionTitle icon={<Thermometer className="h-4 w-4" />}>
        Current conditions · <span className="text-slate-300">{city.city}</span>
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-5">
        <div className="flex h-24 w-24 items-center justify-center rounded-2xl border border-space-700 bg-accent/10">
          <Icon className="h-12 w-12 text-accent" />
        </div>
        <div>
          <div className="text-5xl font-extrabold tracking-tight text-white">
            {cur.temperature_c != null ? `${Math.round(cur.temperature_c)}°` : "—"}
          </div>
          <div className="mt-0.5 text-sm font-medium text-slate-300">{meta.label}</div>
          <div className="text-xs text-slate-500">
            Feels like {cur.apparent_temperature_c != null ? `${Math.round(cur.apparent_temperature_c)}°C` : "—"}
          </div>
        </div>
        <div className="ml-auto hidden shrink-0 flex-col gap-2 text-right sm:flex">
          <div className="text-[11px] text-slate-500">
            <Sunrise className="mr-1 inline h-3.5 w-3.5 text-amber-300" /> Sunrise {shortTime(today.sunrise)}
          </div>
          <div className="text-[11px] text-slate-500">
            <Sunset className="mr-1 inline h-3.5 w-3.5 text-amber-500" /> Sunset {shortTime(today.sunset)}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatBox icon={<Umbrella className="h-3.5 w-3.5 text-accent" />} label="Humidity" value={`${cur.relative_humidity != null ? Math.round(cur.relative_humidity) : "—"}%`} />
        <StatBox icon={<Wind className="h-3.5 w-3.5 text-cyan-400" />} label="Wind" value={`${cur.wind_speed_kmh != null ? Math.round(cur.wind_speed_kmh) : "—"} km/h · ${compass(cur.wind_direction)}`} />
        <StatBox icon={<Gauge className="h-3.5 w-3.5 text-violet-400" />} label="Pressure" value={cur.pressure_hpa != null ? `${Math.round(cur.pressure_hpa)} hPa` : "—"} />
        <StatBox icon={<Cloudy className="h-3.5 w-3.5 text-slate-400" />} label="Cloud cover" value={`${cur.cloud_cover != null ? Math.round(cur.cloud_cover) : "—"}%`} />
        <StatBox icon={<CloudRainWind className="h-3.5 w-3.5 text-sky-400" />} label="Precipitation" value={cur.precipitation_mm != null ? `${cur.precipitation_mm} mm` : "—"} />
        <StatBox icon={<Sun className="h-3.5 w-3.5 text-amber-300" />} label="UV index" value={cur.uv_index != null ? cur.uv_index : "—"} />
        <StatBox icon={<Eye className="h-3.5 w-3.5 text-emerald-400" />} label="Visibility" value={cur.visibility_km != null ? `${Math.round(cur.visibility_km)} km` : "—"} />
        <StatBox icon={<Navigation className="h-3.5 w-3.5 text-slate-400" />} label="Timezone" value={(city.timezone || "UTC").replace("_", " ")} />
      </div>
    </div>
  );
}

function DailyForecast({ days }) {
  if (!days || !days.length) return null;
  return (
    <div className="card p-5">
      <SectionTitle icon={<CloudSun className="h-4 w-4" />}>7-day outlook</SectionTitle>
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-7">
        {days.map((d, i) => {
          const meta = weatherMeta(d.weather_code);
          const Icon = meta.icon;
          let label = `${i + 1}`;
          const date = new Date(`${String(d.date).slice(0, 10)}T12:00:00`);
          if (!Number.isNaN(date.getTime())) label = WEEKDAYS[date.getDay()];
          if (i === 0) label = "Today";
          return (
            <div key={d.date} className={`rounded-2xl border ${i === 0 ? "border-accent/40 bg-accent/5" : "border-space-700 bg-space-850/60"} px-2 py-3`}>
              <div className="text-center text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
              <div className="mt-1 flex justify-center"><Icon className="h-6 w-6 text-accent" /></div>
              <div className="mt-1 text-center text-[11px] text-slate-500">{meta.label}</div>
              <div className="mt-1 text-center text-sm font-bold text-slate-100">
                {d.temperature_max_c != null ? Math.round(d.temperature_max_c) : "—"}°
                <span className="text-slate-500">/{d.temperature_min_c != null ? Math.round(d.temperature_min_c) : "—"}°</span>
              </div>
              <div className="mt-1 flex items-center justify-center gap-1 text-[10px] text-slate-500">
                <Umbrella className="h-3 w-3 text-accent" />
                {d.precipitation_probability_max != null ? Math.round(d.precipitation_probability_max) : "—"}%
                <Wind className="ml-1 h-3 w-3 text-cyan-400" />
                {d.wind_speed_max_kmh != null ? Math.round(d.wind_speed_max_kmh) : "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HourlyForecast({ hours }) {
  if (!hours || !hours.length) return null;
  const rows = hours.slice(0, 48).map(h => ({
    time: shortTime(h.time),
    t: h.temperature_c != null ? Math.round(h.temperature_c) : null,
    pop: h.precipitation_probability != null ? Math.round(h.precipitation_probability) : null
  }));
  return (
    <div className="card p-5">
      <SectionTitle icon={<CloudRainWind className="h-4 w-4" />}>
        Next 48 hours · temperature & rain probability
      </SectionTitle>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ReLine data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 9 }} interval={3} />
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
            <RTooltip />
            <Line type="monotone" dataKey="t" stroke="#22d3ee" strokeWidth={2} dot={false} name="Temp °C" />
            <Line type="monotone" dataKey="pop" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Rain %" />
          </ReLine>
        </ResponsiveContainer>
      </div>
    </div>
  );
}