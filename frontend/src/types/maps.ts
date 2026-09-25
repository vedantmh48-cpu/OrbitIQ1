/**
 * Map Type Catalog & Dynamic Map Renderer - TypeScript models.
 * Mirrors `GET /api/v1/maps/*` contracts.
 */
import type * as GeoJSON from "geojson";
import type { Layer as DeckLayer } from "@deck.gl/core";

// ---------------------------------------------------------------------------
// Catalog models
// ---------------------------------------------------------------------------

export type MapCategory = "general" | "statistical" | "environmental" | "property" | "digital";
export type MapEngine = "maplibre" | "leaflet";
export type OverlayType =
  | "none"
  | "choropleth"
  | "isarithmic"
  | "dots"
  | "symbols"
  | "flow"
  | "heat"
  | "cartogram"
  | "time_series"
  | "dem"
  | "cadastral"
  | "mental"
  | "aerodata"
  | "nautical";
export type OverlayRenderer = "maplibre" | "deck";

export type LegendType = "gradient" | "classes" | "contour" | "symbol";

export interface LegendStop {
  value: number;
  color: string;
  label?: string;
}
export interface LegendItem {
  label: string;
  color: string;
}
export interface LegendContourLevel {
  level: number;
  color: string;
}
export interface LegendSymbolScaleEntry {
  value: number;
  size: number;
  label?: string;
}

export interface LegendSpec {
  type: LegendType;
  label: string;
  unit?: string;
  stops?: LegendStop[];
  items?: LegendItem[];
  levels?: LegendContourLevel[];
  scale?: LegendSymbolScaleEntry[];
}

export interface BaseLayerConfig {
  source: string | null;
  attribution: string;
  engine: MapEngine;
}

export interface OverlayConfig {
  type: OverlayType;
  renderer: OverlayRenderer;
  opacity: number;
  [key: string]: unknown;
}

export interface LayerConfig {
  base: BaseLayerConfig;
  overlay: OverlayConfig;
  temporal: boolean;
  "3d": boolean;
}

export interface MapCatalogEntry {
  map_id: string;
  key: string;
  title: string;
  category: MapCategory;
  summary: string;
  engine: MapEngine;
  tile_url: string | null;
  layer_config: LayerConfig;
  legend: LegendSpec;
  permission_tier: string;
  is_3d_supported: boolean;
  is_temporal: boolean;
  source_types: string[];
  default_opacity: number;
}

export interface CatalogCategoryDescriptor {
  id: MapCategory;
  label: string;
  count: number;
}

export interface CatalogResponse {
  maps: MapCatalogEntry[];
  categories: CatalogCategoryDescriptor[];
  total: number;
}

// ---------------------------------------------------------------------------
// Dynamic layer models
// ---------------------------------------------------------------------------

export interface MapFeatureProps {
  value?: number;
  color?: string;
  class?: string;
  t?: number;
  magnitude?: number;
  elevation?: number;
  [key: string]: unknown;
}

/** Geometry with coordinates (excludes GeometryCollection). */
export type MapGeometry = Exclude<GeoJSON.Geometry, GeoJSON.GeometryCollection>;

export interface MapFeature extends GeoJSON.Feature<MapGeometry> {
  properties: MapFeatureProps;
}

export interface DynamicLayerData {
  type: "FeatureCollection";
  features: MapFeature[];
  frame?: number;
  frames?: number;
  levels?: number[];
  note?: string;
}

export interface LayerResponse {
  entry: MapCatalogEntry;
  data: DynamicLayerData;
  bbox: number[];
}

export interface LayerControlMeta {
  key: string;
  title: string;
  category: MapCategory;
  library: "raster" | "deck" | "maplibre-vector";
}

// ---------------------------------------------------------------------------
// Render-layer models (MapLibre + Deck.gl)
// ---------------------------------------------------------------------------

export interface ActiveMapLayer {
  uid: string;
  entry: MapCatalogEntry;
  kind: "base" | "overlay";
  visible: boolean;
  opacity: number;
  data: DynamicLayerData | null;
  loading: boolean;
  error?: string;
}

/** A concrete deck.gl layer plus an id to update it by. */
export interface DeckRenderLayer {
  id: string;
  layer: DeckLayer;
}

export interface RenderModel {
  /** MapLibre GL style (base raster + vector overlays). */
  style: Record<string, unknown>;
  /** Deck.gl layers consumed by MapLibreOverlay. */
  deckLayers: DeckRenderLayer[];
  /** Legend specs for the active visible map. */
  legends: LegendSpec[];
  /** DEM source id when a 3D terrain entry is the base. */
  demSourceId?: string;
  attribution: string[];
  temporal: boolean;
  frames: number;
  currentFrame: number;
}

export const MAP_CATEGORY_LABELS: Record<MapCategory, string> = {
  general: "General & Core Reference",
  statistical: "Statistical & Data Visualization",
  environmental: "Environmental, Scientific & Applied",
  property: "Special Navigation & Property",
  digital: "Modern Digital & Cognitive",
};

export const MAP_CATEGORY_ORDER: MapCategory[] = [
  "general",
  "statistical",
  "environmental",
  "property",
  "digital",
];

export interface TimeSliceState {
  playing: boolean;
  frame: number;
  frames: number;
  fps: number;
}