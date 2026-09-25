/**
 * MapExplorerCanvas - MapLibre GL JS base engine + Deck.gl renderer sync.
 *
 * * Creates a MapLibre map whose style comes from `useMapStyle` (raster bases,
 *   DEM terrain, in-engine vector overlays).
 * * Attaches a MapLibreOverlay (@deck.gl/maplibre) for Deck.gl renderers
 *   (Heatmap / Dots / Symbols / Flow arcs / Polygon cartograms).
 * * Applies incremental style diffs when the overlay stack changes so the
 *   camera + tiles survive stacking operations.
 */
import { useEffect, useRef } from "react";
import { AttributionControl, GeoJSONSource, Map as MlMap, NavigationControl } from "maplibre-gl";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DeckRenderLayer, RenderModel } from "../../types/maps";

export interface MapExplorerCanvasProps {
  model: RenderModel;
  baseUid: string | null;
  deckLayers: DeckRenderLayer[];
  className?: string;
}

const OWN_LAYER_PREFIXES = ["base", "dem-", "vec-"];

function isOwnLayerId(id: string): boolean {
  return OWN_LAYER_PREFIXES.some((prefix) => id.startsWith(prefix));
}

/** Incremental style application that never rebuilds the tile pipeline. */
function applyStyleDiff(map: MlMap, style: Record<string, unknown>): void {
  const sources = (style.sources ?? {}) as Record<string, any>;
  const layers = (style.layers ?? []) as Record<string, any>[];

  // 1) drop our layers no longer in the style
  for (const layer of map.getStyle().layers) {
    if (isOwnLayerId(layer.id) && !layers.some((l) => l.id === layer.id)) {
      try {
        map.removeLayer(layer.id);
      } catch {
        /* already gone */
      }
    }
  }
  // 2) add / update geojson sources
  for (const [id, src] of Object.entries(sources)) {
    const existing = map.getSource(id);
    if (!existing) {
      try {
        map.addSource(id, src);
      } catch {
        /* ignore transient duplicates */
      }
    } else if (id.startsWith("vec-") && src?.data && typeof (existing as GeoJSONSource).setData === "function") {
      (existing as GeoJSONSource).setData(src.data);
    }
  }
  // 3) remove stale vector sources
  for (const id of Object.keys(map.getStyle().sources)) {
    if (id.startsWith("vec-") && !(id in sources)) {
      try {
        map.removeSource(id);
      } catch {
        /* already gone */
      }
    }
  }
  // 4) add layers / refresh paint
  for (const layer of layers) {
    const id = layer.id as string;
    if (!map.getLayer(id)) {
      try {
        map.addLayer(layer as never);
      } catch {
        /* ignore */
      }
    } else if (layer.paint) {
      for (const [paintKey, value] of Object.entries(layer.paint)) {
        try {
          map.setPaintProperty(id as never, paintKey as never, value as never);
        } catch {
          /* ignore unsupported property */
        }
      }
    }
  }
  // 5) terrain
  try {
    const wants = style.terrain as { source: string } | undefined;
    if (wants && !map.getTerrain()) map.setTerrain(wants);
    if (!wants && map.getTerrain()) map.setTerrain(null);
  } catch {
    /* terrain unavailable */
  }
}

export default function MapExplorerCanvas({ model, baseUid, deckLayers, className = "" }: MapExplorerCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const overlayRef = useRef<MapLibreOverlay | null>(null);
  const lastBaseRef = useRef<string | null>(null);
  const lastStyleSig = useRef("");

  // --- create the engine once -------------------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const map = new MlMap({
      container,
      style: model.style as never,
      center: [78.96, 22.5],
      zoom: 4,
      attributionControl: false,
    });
    map.addControl(new NavigationControl({ showCompass: true }), "top-right");
    map.addControl(new AttributionControl({ compact: true }), "bottom-right");

    const supportsWebGL2 = Boolean(document.createElement("canvas").getContext("webgl2"));
    const overlay = new MapLibreOverlay({ interleaved: supportsWebGL2, layers: [] });
    map.addControl(overlay as never);
    overlayRef.current = overlay;
    mapRef.current = map;
    lastBaseRef.current = baseUid;
    lastStyleSig.current = JSON.stringify(model.style);

    return () => {
      try {
        overlay.finalize?.();
      } catch {
        /* noop */
      }
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- deck.gl layers ---------------------------------------------------------
  useEffect(() => {
    overlayRef.current?.setProps({ layers: deckLayers.map((d) => d.layer) });
  }, [deckLayers]);

  // --- style swaps ------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const sig = JSON.stringify(model.style);
    if (sig === lastStyleSig.current) return;
    lastStyleSig.current = sig;
    if (baseUid !== lastBaseRef.current) {
      // A brand new base map: full style swap (camera is preserved).
      lastBaseRef.current = baseUid;
      map.setStyle(model.style as never);
      return;
    }
    applyStyleDiff(map, model.style);
  }, [model.style, baseUid]);

  return <div ref={containerRef} className={`h-full w-full ${className}`} />;
}