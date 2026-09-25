import { useEffect, useState } from "react";
import {
  FileScan, Boxes, MapPin, FileJson, FileCode2, Ruler, Layers, Activity,
  Droplets, Leaf, Building2, Download, Satellite, Landmark
} from "lucide-react";
import { api, formatNumber } from "../api/client.js";
import { Alert, Badge, Button, Card, SectionTitle, Spinner } from "../components/ui.jsx";
import MapView from "../components/MapView.jsx";

const INDEX_META = {
  ndvi: { icon: Leaf, color: "#22c55e", hint: "Vegetation health" },
  ndwi: { icon: Droplets, color: "#0ea5e9", hint: "Surface water & moisture" },
  ndbi: { icon: Building2, color: "#f97316", hint: "Built-up / impervious" }
};

export default function GeoTools() {
  const [caps, setCaps] = useState(null);
  const [indexes, setIndexes] = useState([]);
  const [tab, setTab] = useState("indices");

  useEffect(() => {
    (async () => {
      try { setCaps(await api.get("/api/geospatial/capabilities")); } catch { /* optional */ }
      try {
        const r = await api.get("/api/geospatial/indexes");
        setIndexes(r.indexes || []);
      } catch { /* optional */ }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="animate-fade-up">
        <div className="section-kicker">Geospatial & remote-sensing tooling</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          GeoTools <span className="gradient-text">Workshop</span>
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Spectral-index engine, GeoTIFF / GIS header parsing, CRS &amp; EPSG detection,
          and WKT / GeoJSON footprint synthesis — grounded in real bytes, honestly labelled.
        </p>
      </div>

      {/* capability chips */}
      <div className="flex flex-wrap gap-2 animate-fade-up" style={{ animationDelay: "0.05s" }}>
        {(caps ? [
          ["geotiff_parse", "GeoTIFF parser", FileScan],
          ["epsg_detection", "EPSG / CRS detection", Landmark],
          ["wkt", "WKT footprints", FileCode2],
          ["geojson_footprint", "GeoJSON footprints", FileJson],
        ] : []).map(([k, label, Icon]) => (
          <span key={k} className="chip !border-emerald-500/40 !text-emerald-400">
            <Icon className="h-3.5 w-3.5" /> {label}
          </span>
        ))}
        <span className="chip !border-accent/40 !text-accent"><Satellite className="h-3.5 w-3.5" /> {indexes.length} spectral indices</span>
      </div>

      {/* tabs */}
      <div className="card !p-2 flex gap-1 overflow-x-auto animate-fade-up" style={{ animationDelay: "0.08s" }}>
        {[
          ["indices", "Spectral index explorer", Activity],
          ["geotiff", "GeoTIFF / GIS parser", FileScan]
        ].map(([id, label, Icon]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium transition ${
              tab === id ? "bg-accent/15 text-accent" : "text-slate-400 hover:bg-space-800 hover:text-slate-200"
            }`}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "indices" && <IndexExplorer indexes={indexes} />}
      {tab === "geotiff" && <GeoTiffParser />}
    </div>
  );
}
/* ------------------------------------------------------------------ */
/* Spectral index explorer                                             */
/* ------------------------------------------------------------------ */

function IndexExplorer({ indexes }) {
  const [index, setIndex] = useState("ndvi");
  const [location, setLocation] = useState("Punjab");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.post(`/api/geospatial/indexes/run?index=${index}&location=${encodeURIComponent(location)}`, {});
      setResult(res);
    } catch (e) {
      setError(e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { run(); /* eslint-disable-next-line */ }, []);

  const meta = INDEX_META[index] || { icon: Activity, color: "#22d3ee" };
  const Icon = meta.icon;

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr] animate-fade-up">
      {/* control panel */}
      <Card className="h-fit">
        <SectionTitle icon={<Activity className="h-4 w-4" />}>Index parameters</SectionTitle>
        <div className="space-y-3">
          <div>
            <label className="label">Index</label>
            <select className="input" value={index} onChange={e => { setIndex(e.target.value); }}>
              {indexes.map(i => (
                <option key={i.id} value={i.id}>{i.id.toUpperCase()} — {i.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Location</label>
            <div className="relative">
              <MapPin className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input className="input !pl-9" value={location} onChange={e => setLocation(e.target.value)} placeholder="e.g. Punjab" />
            </div>
          </div>
          <Button className="w-full" onClick={run} loading={loading}>Compute index</Button>
          {result && (
            <div className="rounded-xl border border-space-700 bg-space-850/60 p-3">
              <div className="font-mono text-xs text-slate-300">{result.formula}</div>
              <div className="mt-1 text-[11px] text-slate-500">Band pair · threshold {result.stats.threshold}</div>
            </div>
          )}
        </div>
      </Card>

      {/* results */}
      <div className="space-y-4">
        {error && <Alert type="error">{error}</Alert>}
        {!result && loading && <Card><div className="flex items-center gap-2"><Spinner label="Computing index…" /></div></Card>}
        {result && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Mean index" value={result.stats.mean_index} icon={<Icon className="h-4 w-4" />} />
              <Stat label="Range" value={`${result.stats.min_index} … ${result.stats.max_index}`} icon={<Ruler className="h-4 w-4" />} />
              <Stat label="Above threshold" value={`${result.stats.positive_cells} cells`} icon={<Layers className="h-4 w-4" />} />
              <Stat label="Flagged area" value={formatNumber(result.stats.positive_area_km2) + " km²"} icon={<MapPin className="h-4 w-4" />} />
            </div>
            <Card className="!p-0 overflow-hidden">
              <div className="flex items-center justify-between border-b px-4 py-2.5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <Icon className="h-4 w-4" style={{ color: meta.color }} /> {index.toUpperCase()} over {result.location}
                </div>
                <Badge color="amber">Simulated</Badge>
              </div>
              <div className="h-[380px]">
                <MapView geojson={result.geojson} op={index} baseLayer="Satellite" showLegend={false} />
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
/* ------------------------------------------------------------------ */
/* GeoTIFF parser                                                      */
/* ------------------------------------------------------------------ */

function GeoTiffParser() {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filename, setFilename] = useState("");

  const parseDemo = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/api/geospatial/demo/parse");
      setInfo(res);
      setFilename("demo-kerala.tif (simulated)");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const onFile = async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const raw = await fetch("/api/geospatial/parse", {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("satquery_access") || ""}` },
        body: fd
      });
      const json = await raw.json();
      if (!raw.ok) throw new Error(json.detail || "Parse failed");
      setInfo(json);
      setFilename(file.name);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (e.target) e.target.value = "";
    }
  };

  useEffect(() => { parseDemo(); }, []);

  return (
    <div className="space-y-4 animate-fade-up">
      {error && <Alert type="error">{error}</Alert>}

      {/* controls */}
      <Card>
        <SectionTitle icon={<FileScan className="h-4 w-4" />}>Parse a GeoTIFF raster header</SectionTitle>
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn-ghost !cursor-pointer">
            <FileScan className="h-4 w-4" /> Choose .tif…
            <input type="file" accept=".tif,.tiff" className="hidden" onChange={onFile} />
          </label>
          <Button variant="ghost" onClick={parseDemo} loading={loading}>
            <Satellite className="h-4 w-4" /> Parse demo GeoTIFF
          </Button>
          <a href="/api/geospatial/demo" className="btn-ghost !no-underline">
            <Download className="h-4 w-4" /> Download demo .tif
          </a>
          <span className="text-xs text-slate-500">Pure tag-level parsing — no GDAL required. Max 25 MB.</span>
        </div>
      </Card>

      {loading && <Card><div className="flex items-center gap-2"><Spinner label="Parsing header tags…" /></div></Card>}

      {info && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* specs */}
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <SectionTitle icon={<FileScan className="h-4 w-4" />}>Raster specification</SectionTitle>
              {info.simulated && <Badge color="amber">Simulated demo</Badge>}
            </div>
            <p className="mb-3 truncate font-mono text-[11px] text-slate-500">{filename}</p>
            <SpecRow label="EPSG" value={info.crs?.epsg ? `${info.crs.epsg} — ${info.crs.name}` : "—"} />
            <SpecRow label="Model type" value={info.crs?.model_type} />
            <SpecRow label="Dimensions" value={`${info.dimensions?.width} × ${info.dimensions?.height} × ${info.dimensions?.bands} band(s)`} />
            <SpecRow label="Bits / sample" value={info.bits_per_sample} />
            <SpecRow label="Compression" value={info.compression} />
            <SpecRow label="Angular units" value={info.crs?.angular_units} />
            <SpecRow label="Linear units" value={info.crs?.linear_units} />
            {info.crs?.citation && <SpecRow label="Citation" value={info.crs.citation} />}
            <div className="mt-3 grid grid-cols-2 gap-2">
              {info.footprint_wkt && (
                <div className="rounded-xl border border-space-700 bg-space-850/60 p-2.5">
                  <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <FileCode2 className="h-3 w-3" /> WKT footprint
                  </div>
                  <code className="mt-1 block break-all font-mono text-[10px] text-slate-300">{info.footprint_wkt}</code>
                </div>
              )}
              {info.bounds && (
                <div className="rounded-xl border border-space-700 bg-space-850/60 p-2.5">
                  <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Boxes className="h-3 w-3" /> Bounding box (lon/lat)
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-slate-300">
                    {info.bounds.min_lng}, {info.bounds.min_lat}<br />{info.bounds.max_lng}, {info.bounds.max_lat}
                  </div>
                </div>
              )}
            </div>
          </Card>
{/* footprint map + geokeys */}
          <div className="space-y-4">
            <Card className="!p-0 overflow-hidden">
              <div className="flex items-center justify-between border-b px-4 py-2.5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <MapPin className="h-4 w-4 text-accent" /> Raster footprint
                </div>
                <Badge color="slate">EPSG:{info.crs?.epsg}</Badge>
              </div>
              <div className="h-[250px]">
                <MapView geojson={info.footprint_geojson} op="object-detection" baseLayer="Satellite" showLegend={false} />
              </div>
            </Card>
            <Card>
              <SectionTitle icon={<Layers className="h-4 w-4" />}>GeoKey directory (raw)</SectionTitle>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {Object.entries(info.crs?.geo_keys || {}).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-2 rounded-lg border border-space-700 bg-space-850/40 px-2 py-1.5">
                    <span className="truncate text-[11px] text-slate-400">{k}</span>
                    <span className="font-mono text-[11px] text-accent">{v}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, icon }) {
  return (
    <div className="card p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        <span className="text-accent">{icon}</span> {label}
      </div>
      <div className="mt-1 text-base font-bold text-white">{value}</div>
    </div>
  );
}

function SpecRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-space-800 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-200">{value || "—"}</span>
    </div>
  );
}