/**
 * useMapStyle - Map Engine Adapter Logic.
 *
 * Turns the active base map + overlay stack into:
 *  - a MapLibre GL style (raster bases, vector overlays, DEM terrain source)
 *  - matching Deck.gl layers (Heatmap, Dots/Proportional symbols, Arc flows,
 *    Polygon cartograms) consumed through MapLibreOverlay.
 */
import { useMemo } from "react";
import { ArcLayer, ScatterplotLayer, PolygonLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Layer as DeckLayer } from "@deck.gl/core";
import type {
  ActiveMapLayer,
  DeckRenderLayer,
  DynamicLayerData,
  LegendSpec,
  MapFeature,
  OverlayType,
  RenderModel,
} from "../types/maps";
import { filterFrame } from "../api/maps";

const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";

/** Facilities served by the Deck.gl renderer. */
const DECK_TYPES: OverlayType[] = ["heat", "dots", "symbols", "flow", "cartogram", "time_series", "nautical"];

export function isDeckOverlay(overlay: OverlayType): boolean {
  return DECK_TYPES.includes(overlay);
}

export function hexToRgba(hex: string, alpha = 1): [number, number, number, number] {
  const value = hex.replace("#", "");
  if (value.length === 6) {
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return [r, g, b, Math.round(Math.max(0, Math.min(1, alpha)) * 255)];
  }
  return [34, 211, 238, Math.round(alpha * 255)];
}

// ---------------------------------------------------------------------------
// MapLibre style construction
// ---------------------------------------------------------------------------

function rasterSource(url: string | null): Record<string, unknown> {
  return url
    ? { type: "raster", tiles: [url], tileSize: 256, maxzoom: 19 }
    : { type: "raster", tiles: [""], tileSize: 256 };
}

function vectorOverlayLayers(
  layers: ActiveMapLayer[]
): { sources: Record<string, unknown>; layers: Record<string, unknown>[] } {
  const sources: Record<string, unknown> = {};
  const out: Record<string, unknown>[] = [];
  for (const layer of layers) {
    if (!layer.visible || !layer.data || layer.data.features.length === 0) continue;
    const overlayType = layer.entry.layer_config.overlay.type;
    if (isDeckOverlay(overlayType)) continue; // handled by Deck.gl
    const sourceId = `vec-${layer.uid}`;
    sources[sourceId] = { type: "geojson", data: layer.data };
    const fillColor = ["coalesce", ["get", "color"], "#22d3ee"] as unknown;
    const lineColor = ["coalesce", ["get", "color"], "#67e8f9"] as unknown;
    if (overlayType === "isarithmic") {
      out.push({
        id: `${sourceId}-line`,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": lineColor,
          "line-width": ["coalesce", ["get", "level"], 2] as unknown,
          "line-opacity": layer.opacity,
        },
      });
    } else {
      out.push(
        {
          id: `${sourceId}-fill`,
          type: "fill",
          source: sourceId,
          paint: { "fill-color": fillColor, "fill-opacity": layer.opacity * 0.85 },
        },
        {
          id: `${sourceId}-line`,
          type: "line",
          source: sourceId,
          paint: {
            "line-color": "#0f172a",
            "line-width": 0.6,
            "line-opacity": Math.max(0.15, layer.opacity * 0.6),
          },
        }
      );
    }
  }
  return { sources, layers: out };
}

function buildStyle(base: ActiveMapLayer | null, overlays: ActiveMapLayer[]): Record<string, unknown> {
  const baseUrl = base?.entry.tile_url || null;
  const baseSourceId = "base-raster";
  const sources: Record<string, unknown> = {};
  const mapLayers: Record<string, unknown>[] = [];

  if (baseUrl) {
    sources[baseSourceId] = {
      ...rasterSource(baseUrl),
      attribution: base?.entry.layer_config.base.attribution || "",
    };
    mapLayers.push({
      id: "base",
      type: "raster",
      source: baseSourceId,
      paint: { "raster-opacity": base && base.visible ? (base.opacity ?? 1) : 0 },
    });
    mapLayers.push({
      id: "base-background",
      type: "background",
      paint: { "background-color": "#0a1220" },
    });
  } else {
    // No base selected: render a clean deep-space background instead of an
    // empty raster source (which would try to decode the app page as a tile).
    mapLayers.push({
      id: "base",
      type: "background",
      paint: { "background-color": "#0a1220" },
    });
  }

  // DEM terrain (raster-dem) activation for DEM / hillshade bases.
  const baseUsesDem =
    (base?.entry.tile_url ?? "").includes("terrarium") ||
    base?.entry.layer_config.overlay.type === "dem";
  const demSourceId = "dem-source";
  if (baseUsesDem) {
    sources[demSourceId] = { type: "raster-dem", tiles: [DEM_TILES], encoding: "terrarium", maxzoom: 14 };
    mapLayers.push({
      id: "dem-hillshade",
      type: "hillshade",
      source: demSourceId,
      paint: {
        "hillshade-exaggeration": 0.4,
        "hillshade-highlight-color": "#d8f3ff",
        "hillshade-shadow-color": "#10202e",
      },
    });
  }

  const vec = vectorOverlayLayers(overlays);
  Object.assign(sources, vec.sources);
  mapLayers.push(...vec.layers);
  return {
    version: 8,
    name: base?.entry.title || "OrbitIQ",
    sources,
    layers: mapLayers,
    terrain: baseUsesDem
      ? { source: demSourceId, exaggeration: base?.entry.is_3d_supported ? 1.75 : 0.6 }
      : undefined,
  };
}

// ---------------------------------------------------------------------------
// Deck.gl layer construction
// ---------------------------------------------------------------------------

function pointCoords(feat: MapFeature): [number, number] {
  const c = feat.geometry.coordinates;
  return [c[0] as number, c[1] as number];
}

function affinity(f: MapFeature): number {
  const v = Number(f.properties.value ?? 10);
  return Math.min(28, 2 + Math.sqrt(v) * 2.2);
}

function buildDeckLayers(overlays: ActiveMapLayer[], frame: number): DeckRenderLayer[] {
  const layers: DeckRenderLayer[] = [];
  for (const layer of overlays) {
    if (!layer.visible || !layer.data) continue;
    const type = layer.entry.layer_config.overlay.type;
    if (!isDeckOverlay(type)) continue;
    const data = layer.entry.is_temporal
      ? filterFrame(layer.data, frame, layer.data.frames || 1).features
      : layer.data.features;
    if (!data.length) continue;
    const id = `deck-${layer.uid}`;
    const opacity = layer.opacity;

    let deckLayer: DeckLayer;
    switch (type) {
      case "heat":
        deckLayer = new HeatmapLayer({
          id,
          data,
          getPosition: pointCoords,
          getWeight: (f: MapFeature) => Number(f.properties.value ?? 1) / 100,
          radiusPixels: 42,
          opacity,
          intensity: 1.1,
          threshold: 0.04,
        });
        break;
      case "dots":
        deckLayer = new ScatterplotLayer({
          id,
          data,
          getPosition: pointCoords,
          getRadius: (f: MapFeature) => (f.properties.class === "event" ? 4 : 2.2),
          getFillColor: (f: MapFeature) =>
            f.properties.class === "event"
              ? [244, 63, 94, Math.round(opacity * 255)]
              : [34, 211, 238, Math.round(opacity * 190)],
          stroked: false,
          radiusUnits: "pixels",
        });
        break;
      case "symbols":
      case "nautical":
        deckLayer = new ScatterplotLayer({
          id,
          data,
          getPosition: pointCoords,
          getRadius: affinity,
          getFillColor: (f: MapFeature) => hexToRgba(f.properties.color || "#22d3ee", opacity),
          getLineColor: [255, 255, 255, 180],
          getLineWidth: 1,
          stroked: true,
          radiusUnits: "pixels",
        });
        break;
      case "flow": {
        const flows = data
          .map((f) => {
            const coords = f.geometry.coordinates;
            if (!Array.isArray(coords) || coords.length < 2) return null;
            return {
              start: coords[0] as unknown as [number, number],
              end: coords[coords.length - 1] as unknown as [number, number],
              magnitude: Number(f.properties.magnitude ?? 5),
            };
          })
          .filter(Boolean) as { start: [number, number]; end: [number, number]; magnitude: number }[];
        deckLayer = new ArcLayer({
          id,
          data: flows,
          getSourcePosition: (d) => d.start,
          getTargetPosition: (d) => d.end,
          getSourceColor: [34, 211, 238, 160],
          getTargetColor: [251, 146, 60, 200],
          getWidth: (d) => Math.max(0.5, d.magnitude / 5),
          widthUnits: "pixels",
          opacity,
        });
        break;
      }
      case "cartogram":
        deckLayer = new PolygonLayer({
          id,
          data,
          getPolygon: (f: MapFeature) => f.geometry.coordinates as never,
          getFillColor: (f: MapFeature) => hexToRgba(f.properties.color || "#1d4ed8", opacity),
          getLineColor: [15, 23, 42, 200],
          lineWidthUnits: "pixels",
          getLineWidth: 0.75,
          stroked: true,
          filled: true,
          opacity,
        });
        break;
      case "time_series":
        deckLayer = new ScatterplotLayer({
          id,
          data,
          getPosition: pointCoords,
          getRadius: 4,
          getFillColor: (f: MapFeature) => hexToRgba(f.properties.color || "#7c3aed", opacity),
          radiusUnits: "pixels",
        });
        break;
      default:
        continue;
    }
    layers.push({ id, layer: deckLayer });
  }
  return layers;
}
// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface MapStyleInput {
  base: ActiveMapLayer | null;
  overlays: ActiveMapLayer[];
  timeIndex: number;
}

export function useMapStyle({ base, overlays, timeIndex }: MapStyleInput): RenderModel {
  const visibleOverlays = overlays.filter((l) => l.visible && !l.loading);
  // MapLibre style only depends on base + overlay stack (NOT the time frame)
  // so time-series playback never forces a tile reload.
  const style = useMemo(() => buildStyle(base, visibleOverlays), [base, visibleOverlays]);
  const deckLayers = useMemo(
    () => buildDeckLayers(visibleOverlays, timeIndex),
    [visibleOverlays, timeIndex]
  );
  return useMemo(() => {
    const temporal = (base?.entry.is_temporal ?? false) || overlays.some((l) => l.entry.is_temporal);
    const frames = Math.max(
      ...visibleOverlays.map((l) => l.data?.frames ?? 1).concat(temporal ? [12] : [1])
    );
    const legends: LegendSpec[] = [];
    if (base) legends.push(base.entry.legend);
    for (const layer of visibleOverlays) legends.push(layer.entry.legend);
    const attribution = [base?.entry.layer_config.base.attribution, "deck.gl"]
      .filter(Boolean) as string[];
    return {
      style,
      deckLayers,
      legends,
      demSourceId: (style.terrain as { source?: string } | undefined)?.source,
      attribution,
      temporal,
      frames,
      currentFrame: timeIndex,
    };
  }, [base, visibleOverlays, overlays, timeIndex, style, deckLayers]);
}
