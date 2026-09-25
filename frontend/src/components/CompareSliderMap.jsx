import { useEffect, useRef, useState } from "react";
import {
  GeoJSON, ImageOverlay, MapContainer, Rectangle, TileLayer, useMap
} from "react-leaflet";
import { ChevronsLeftRight, Layers } from "lucide-react";

const DARK_TILES = {
  url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  attribution: "&copy; OSM &copy; CARTO"
};

function boundsFromBbox(bbox) {
  return [
    [bbox.min_lat, bbox.min_lng],
    [bbox.max_lat, bbox.max_lng]
  ];
}

/** Dedicated panes so the AFTER overlay can be CSS-clipped per slider %. */
function PreparePanes({ pos }) {
  const map = useMap();
  useEffect(() => {
    let before = map.getPane("beforePane");
    if (!before) before = map.createPane("beforePane");
    before.style.zIndex = "210";
    let after = map.getPane("afterPane");
    if (!after) after = map.createPane("afterPane");
    after.style.zIndex = "211";
    after.style.clipPath = `inset(0 0 0 ${pos}%)`;
  }, [map, pos]);
  return null;
}

function FitToBbox({ bbox, padding = 24 }) {
  const map = useMap();
  useEffect(() => {
    if (!bbox) return;
    map.fitBounds(
      [
        [bbox.min_lat, bbox.min_lng],
        [bbox.max_lat, bbox.max_lng]
      ],
      { padding: [padding, padding], maxZoom: 14 }
    );
  }, [map, bbox, padding]);
  return null;
}

const HEATMAP_LEGEND = [
  ["Loss", "#1e3a8a"],
  ["", "#3b82f6"],
  ["Moderate", "#22d3ee"],
  ["", "#f59e0b"],
  ["Gain", "#b91c1c"]
];

/**
 * CompareSliderMap — before/after satellite comparison with a draggable
 * divider, togglable change-heatmap / magnitude overlays and hotspot cells.
 */
export default function CompareSliderMap({
  bbox,
  beforeUrl,
  afterUrl,
  heatmapUrl,
  magnitudeUrl,
  showHeatmap = false,
  showMagnitude = false,
  heatOpacity = 0.65,
  hotspots = null,
  showHotspots = true
}) {
  const [pos, setPos] = useState(50);
  const [dragging, setDragging] = useState(false);
  const wrapRef = useRef(null);

  const updateFromClientX = clientX => {
    const el = wrapRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setPos(Math.max(4, Math.min(96, pct)));
  };

  const allowDrag = e => {
    // Only start from the divider handle; never hijack map panning.
    if (e.target.closest(".cmp-handle")) {
      updateFromClientX(e.clientX);
      setDragging(true);
      e.preventDefault();
    }
  };

  useEffect(() => {
    if (!dragging) return undefined;
    const move = e => updateFromClientX(e.clientX);
    const up = () => setDragging(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [dragging]);

  if (!bbox) return null;

  return (
    <div
      ref={wrapRef}
      className="relative h-full w-full overflow-hidden rounded-xl"
      onPointerDown={allowDrag}
      role="group"
      aria-label="Before/after comparison map"
    >
      <MapContainer
        center={[
          bbox.min_lat + (bbox.max_lat - bbox.min_lat) / 2,
          bbox.min_lng + (bbox.max_lng - bbox.min_lng) / 2
        ]}
        zoom={12}
        className="h-full w-full"
        zoomControl={false}
        attributionControl={false}
        style={{ background: "#0b1220" }}
      >
        <TileLayer url={DARK_TILES.url} attribution={DARK_TILES.attribution} />
        <PreparePanes pos={pos} />
        <FitToBbox bbox={bbox} />

        {/* clipped left/right imagery */}
        {beforeUrl && (
          <ImageOverlay
            url={beforeUrl}
            bounds={boundsFromBbox(bbox)}
            pane="beforePane"
            opacity={1}
          />
        )}
        {afterUrl && (
          <ImageOverlay
            url={afterUrl}
            bounds={boundsFromBbox(bbox)}
            pane="afterPane"
            opacity={1}
          />
        )}

        {/* spectrally-derived overlays */}
        {showHeatmap && heatmapUrl && (
          <ImageOverlay
            url={heatmapUrl}
            bounds={boundsFromBbox(bbox)}
            opacity={heatOpacity}
          />
        )}
        {showMagnitude && magnitudeUrl && (
          <ImageOverlay
            url={magnitudeUrl}
            bounds={boundsFromBbox(bbox)}
            opacity={Math.min(0.9, heatOpacity + 0.15)}
          />
        )}

        {/* changed-cell detector grid */}
        {showHotspots && hotspots?.features?.length > 0 && (
          <GeoJSON
            data={hotspots}
            style={f => ({
              color: f.properties?.sign === "gain" ? "#f97316" : "#38bdf8",
              weight: 0.4,
              fillColor: f.properties?.sign === "gain" ? "#f97316" : "#38bdf8",
              fillOpacity: 0.28
            })}
          />
        )}

        <Rectangle
          bounds={boundsFromBbox(bbox)}
          pathOptions={{ color: "#22d3ee", weight: 1.2, dashArray: "5 6", fill: false }}
        />
      </MapContainer>

      {/* draggable divider */}
      <div
        className="pointer-events-none absolute inset-y-0 z-[500] w-0.5 bg-cyan-300/90 shadow-[0_0_8px_rgba(34,211,238,0.9)]"
        style={{ left: `${pos}%` }}
      >
        <div className="cmp-handle pointer-events-auto absolute left-1/2 top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border border-cyan-300/70 bg-space-900/90 shadow-lg backdrop-blur">
          <ChevronsLeftRight className="h-4 w-4 text-cyan-300" />
        </div>
      </div>

      {/* date / layer badges */}
      <div className="pointer-events-none absolute left-2 top-2 z-[550] flex gap-2 text-[11px] font-semibold">
        <span className="rounded-full bg-slate-950/80 px-2.5 py-1 text-cyan-300 ring-1 ring-cyan-400/40 backdrop-blur">
          Before
        </span>
        <span className="rounded-full bg-slate-950/80 px-2.5 py-1 text-amber-300 ring-1 ring-amber-400/40 backdrop-blur">
          After
        </span>
      </div>

      {/* legend */}
      <div className="pointer-events-none absolute bottom-2 left-2 z-[550] rounded-lg border border-space-700 bg-space-900/85 px-2.5 py-2 text-[10px] text-slate-300 backdrop-blur">
        <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-400">
          <Layers className="h-3 w-3" /> Change intensity
        </div>
        <div className="flex items-center gap-1">
          {HEATMAP_LEGEND.map(([label, color], i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
              {label && <span>{label}</span>}
            </span>
          ))}
        </div>
      </div>

      {/* slider */}
      <div className="pointer-events-none absolute bottom-3 left-1/2 z-[550] w-[min(84%,420px)] -translate-x-1/2">
        <input
          type="range"
          min={4}
          max={96}
          value={Math.round(pos)}
          onChange={e => setPos(Number(e.target.value))}
          aria-label="Compare position"
          className="w-full cursor-pointer appearance-none rounded-full bg-slate-700/40 accent-cyan-300"
        />
      </div>
    </div>
  );
}