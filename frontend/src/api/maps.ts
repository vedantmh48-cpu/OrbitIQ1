/**
 * Typed client for the map catalog and dynamic layer endpoints.
 */
import { api } from "./client";
import type {
  CatalogResponse,
  DynamicLayerData,
  LayerResponse,
  MapCatalogEntry,
} from "../types/maps";

interface CatalogParams {
  category?: MapCatalogEntry["category"];
  q?: string;
}

export async function fetchCatalog(params: CatalogParams = {}): Promise<CatalogResponse> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.q) query.set("q", params.q);
  const suffix = query.toString();
  return api.get<CatalogResponse>(`/api/v1/maps/catalog${suffix ? `?${suffix}` : ""}`);
}

export interface LayerParams {
  key: string;
  bbox?: string;
  count?: number;
  time_index?: number;
  dynamic?: boolean;
}

export async function fetchLayer(params: LayerParams): Promise<LayerResponse> {
  const query = new URLSearchParams();
  if (params.bbox) query.set("bbox", params.bbox);
  if (params.count != null) query.set("count", String(Math.min(params.count, 2000)));
  if (params.time_index != null) query.set("time_index", String(params.time_index));
  if (params.dynamic === false) query.set("dynamic", "false");
  const suffix = query.toString();
  return api.get<LayerResponse>(
    `/api/v1/maps/layers/${encodeURIComponent(params.key)}${suffix ? `?${suffix}` : ""}`
  );
}

/**
 * Local data re-slice used by the Time-Series playback: fetch the frame's
 * static GeoJSON once, then filter by `properties.t` client-side.
 */
export function filterFrame(data: DynamicLayerData, frame: number, frames: number): DynamicLayerData {
  if (!data || !data.features) return data;
  const bucket = Math.max(0, Math.min(frames - 1, frame));
  const target = data.frames && data.frames > 1 ? (bucket / Math.max(data.frames - 1, 1)) : bucket;
  return {
    ...data,
    frame: frame,
    frames: frames,
    features: data.features.filter((feat) => {
      const t = feat.properties?.t;
      if (typeof t !== "number") return true;
      const expected = Math.round(target * 100) / 100;
      return Math.abs(t - expected) < 0.25; // tolerance window
    }),
  };
}