import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, GeoJSON, Rectangle as Rect, Tooltip, useMap } from "react-leaflet";

const TILES = {
  Dark: { url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attribution: "&copy; OSM &copy; CARTO" },
  Satellite: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Esri, Maxar, Earthstar" },
  Light: { url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", attribution: "&copy; CARTO &copy; OSM" }
};

const DEFAULT = {
  "flood-mapping": { color: "#38bdf8", weight: 0.6, fillOpacity: 0.65 },
  "change-detection": { color: "#fb923c", weight: 0.6, fillOpacity: 0.6 },
  "classification": { color: "#4ade80", weight: 0.5, fillOpacity: 0.55 },
  "fusion": { color: "#c084fc", weight: 0.6, fillOpacity: 0.6 },
  "terrain": { color: "#a8a29e", weight: 0.5, fillOpacity: 0.7 },
  "object-detection": { color: "#facc15", weight: 0, fillOpacity: 0.9 },
  "real-events": { color: "#f43f5e", weight: 0, fillOpacity: 0.9 }
};

const LEGENDS = {
  "flood-mapping": [["Severe", "#8b5cf6"], ["High", "#ef4444"], ["Moderate", "#f59e0b"], ["Minor", "#0ea5e9"]],
  classification: [
    ["Dense vegetation", "#22c55e"], ["Moderate vegetation", "#84cc16"],
    ["Water", "#0ea5e9"], ["Open water", "#38bdf8"],
    ["Built-up", "#e2e8f0"], ["Barren / dry", "#d6d3d1"]
  ],
  "change-detection": [["Expansion / gain", "#f97316"], ["Reduction / loss", "#38bdf8"]],
  "object-detection": [["Detected target", "#facc15"]],
  "real-events": [["Live observation", "#f43f5e"]],
  ndvi: [["Healthy vegetation", "#22c55e"], ["Sparse / bare / water", "#a3a380"]],
  ndwi: [["Open water / high moisture", "#0ea5e9"], ["Dry surface", "#d6d3d1"]],
  ndbi: [["Built-up / urban", "#f97316"], ["Vegetated / non-urban", "#84cc16"]],
  "sar-backscatter": [
    ["Built-up corner reflectors", "#f43f5e"],
    ["Rough / vegetation", "#f59e0b"],
    ["Smooth / bare", "#84cc16"],
    ["Open water (low σ⁰)", "#0ea5e9"]
  ]
};

function featureColor(feature, op) {
  const p = feature.properties || {};
  if (op === "flood-mapping" && p.value != null) {
    const v = Number(p.value);
    if (v >= 0.82) return "#8b5cf6";
    if (v >= 0.68) return "#ef4444";
    if (v >= 0.52) return "#f59e0b";
    return "#0ea5e9";
  }
  if (op === "classification" && p.class) {
    const map = {
      "Open water": "#38bdf8", "Flooded vegetation": "#34d399",
      "Dry land": "#a3a380", "Built-up": "#e2e8f0",
      "Dense vegetation": "#22c55e", "Moderate vegetation": "#84cc16",
      "Barren / urban": "#d6d3d1", Water: "#0ea5e9"
    };
    return map[p.class] || "#22c55e";
  }
  if (op === "change-detection" && p.value != null) return Number(p.value) > 0 ? "#f97316" : "#38bdf8";
  if (op === "real-events") return p.mag != null && p.mag >= 5 ? "#f43f5e" : "#fb923c";
  return (DEFAULT[op] || DEFAULT["flood-mapping"]).color;
}

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 13 });
  }, [bounds, map]);
  return null;
}

function BoundsMarker({ bbox }) {
  if (!bbox) return null;
  return (
    <Rect
      bounds={[[bbox.min_lat, bbox.min_lng], [bbox.max_lat, bbox.max_lng]]}
      pathOptions={{ color: "#22d3ee", weight: 1, dashArray: "4 6", fill: false }}
    />
  );
}

export default function MapView({
  geojson,
  layers = [],
  bbox,
  op = "flood-mapping",
  baseLayer = "Dark",
  showBounds = true,
  showLegend = true,
  legendColors = null,
  height = "100%",
  className = ""
}) {
  const bounds = useMemo(() => {
    if (geojson && geojson.features?.length) {
      const pts = [];
      for (const f of geojson.features) collectCoords(f.geometry, pts);
      if (pts.length) {
        const lats = pts.map(p => p[0]);
        const lngs = pts.map(p => p[1]);
        return [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]];
      }
    }
    if (bbox) return [[bbox.min_lat, bbox.min_lng], [bbox.max_lat, bbox.max_lng]];
    return [[-30, -140], [55, 160]];
  }, [geojson, bbox]);

  const tile = TILES[baseLayer] || TILES.Light;
  const baseStyle = DEFAULT[op] || DEFAULT["flood-mapping"];
  const legend = LEGENDS[op] || (legendColors ? Object.entries(legendColors) : null);

  return (
    <div className="relative h-full w-full">
      <MapContainer center={[20, 40]} zoom={3} className={`z-0 h-full w-full ${className}`} style={{ height }}>
        <TileLayer url={tile.url} attribution={tile.attribution} />
        <FitBounds bounds={bounds} />
        {showBounds && <BoundsMarker bbox={bbox} />}

        {layers.map(l => (
          <GeoJSON
            key={l.id}
            data={l.geojson}
            style={{ color: "#67e8f9", weight: 0.5, fillColor: "#22d3ee", fillOpacity: 0.22, opacity: 0.7 }}
          >
            <Tooltip sticky>{l.name}</Tooltip>
          </GeoJSON>
        ))}

        {geojson && geojson.features?.length > 0 && (
          <GeoJSON
            data={geojson}
            style={feature => {
              const c = featureColor(feature, op);
              return { ...baseStyle, fillColor: c, color: c };
            }}
            pointToLayer={(feature, latlng) =>
              new window.L.CircleMarker(latlng, {
                radius: 5, color: "#fff", weight: 1,
                fillColor: featureColor(feature, op), fillOpacity: 0.9
              })
            }
          />
        )}
      </MapContainer>
      {showLegend && legend && (
        <div className="map-legend">
          {legend.map(([label, color]) => (
            <div key={label} className="flex items-center">
              <span className="sw" style={{ background: color }} />{label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function collectCoords(geometry, out) {
  if (!geometry) return;
  const { type, coordinates } = geometry;
  if (type === "Point") out.push([coordinates[1], coordinates[0]]);
  else if (type === "Polygon") {
    for (const ring of coordinates) for (const [lng, lat] of ring) out.push([lat, lng]);
  } else if (type === "MultiPolygon") {
    for (const poly of coordinates) for (const ring of poly) for (const [lng, lat] of ring) out.push([lat, lng]);
  } else if (type === "MultiPoint") {
    for (const [lng, lat] of coordinates) out.push([lat, lng]);
  }
}