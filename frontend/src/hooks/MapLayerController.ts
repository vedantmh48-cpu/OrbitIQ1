/**
 * MapLayerController - real-time layer switching / stacking / blending.
 *
 * Owns:
 *  - the active base map entry
 *  - an ordered overlay stack (add / remove / reorder / opacity / visibility)
 *  - recent + favorite map types (localStorage)
 *  - time-slice index for temporal map types
 *
 * Feeds `useMapStyle` so every change is reflected in the render engine.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchLayer } from "../api/maps";
import { useMapStyle } from "./useMapStyle";
import type {
  ActiveMapLayer,
  CatalogCategoryDescriptor,
  MapCatalogEntry,
  RenderModel,
} from "../types/maps";

export const DEFAULT_BBOX = "68,6,98,38";

const PREFS_KEY = "satquery_map_prefs";
const TIME_FRAMES_DEFAULT = 12;

interface PersistedPrefs {
  recents: string[];
  favorites: string[];
}

function loadPrefs(): PersistedPrefs {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || '{"recents":[],"favorites":[]}');
  } catch {
    return { recents: [], favorites: [] };
  }
}

function savePrefs(prefs: PersistedPrefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable */
  }
}

function makeLayer(entry: MapCatalogEntry, kind: "base" | "overlay"): ActiveMapLayer {
  return {
    uid: `${kind}-${entry.key}-${Math.random().toString(36).slice(2, 8)}`,
    entry,
    kind,
    visible: true,
    opacity: entry.default_opacity ?? 0.8,
    data: null,
    loading: false,
  };
}

export interface CatalogCache {
  entries: MapCatalogEntry[];
  categories: CatalogCategoryDescriptor[];
}

export interface MapLayerControllerOutput {
  base: ActiveMapLayer | null;
  overlays: ActiveMapLayer[];
  recents: MapCatalogEntry[];
  favorites: MapCatalogEntry[];
  timeIndex: number;
  frames: number;
  model: RenderModel;

  setBase: (entry: MapCatalogEntry) => void;
  toggleOverlay: (entry: MapCatalogEntry) => void;
  removeOverlay: (uid: string) => void;
  moveOverlay: (uid: string, direction: -1 | 1) => void;
  setOverlayOpacity: (uid: string, opacity: number) => void;
  setOverlayVisible: (uid: string, visible: boolean) => void;
  setBaseOpacity: (uid: string, opacity: number) => void;
  setBaseVisible: (uid: string, visible: boolean) => void;
  setTimeIndex: (index: number) => void;
  toggleFavorite: (key: string) => void;
  removeBase: () => void;
  setBbox: (bbox: string) => void;
  refreshData: () => Promise<void>;
  /** Map entries available to the user (catalog cache). */
  catalog: CatalogCache | null;
  loadCatalog: () => Promise<void>;
}
export function MapLayerController() {
  const [prefs, setPrefs] = useState<PersistedPrefs>(loadPrefs);
  const [base, setBaseRaw] = useState<ActiveMapLayer | null>(null);
  const [overlays, setOverlays] = useState<ActiveMapLayer[]>([]);
  const [timeIndex, setTimeIndex] = useState(0);
  const [bbox, setBboxState] = useState(DEFAULT_BBOX);
  const [catalog, setCatalog] = useState<CatalogCache | null>(null);
  const bboxRef = useRef(bbox);
  bboxRef.current = bbox;

  const loadCatalog = useCallback(async () => {
    if (catalog) return;
    try {
      const { fetchCatalog } = await import("../api/maps");
      const res = await fetchCatalog({});
      setCatalog({ entries: res.maps, categories: res.categories });
    } catch {
      setCatalog({ entries: [], categories: [] });
    }
  }, [catalog]);

  useEffect(() => {
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pushRecent = useCallback((key: string) => {
    setPrefs((p) => {
      const recents = [key, ...p.recents.filter((k) => k !== key)].slice(0, 5);
      savePrefs({ ...p, recents });
      return { ...p, recents };
    });
  }, []);

  const toggleFavorite = useCallback((key: string) => {
    setPrefs((p) => {
      const favorites = p.favorites.includes(key)
        ? p.favorites.filter((k) => k !== key)
        : [key, ...p.favorites];
      savePrefs({ ...p, favorites });
      return { ...p, favorites };
    });
  }, []);

  const fetchForLayer = useCallback(
    async (layer: ActiveMapLayer): Promise<ActiveMapLayer> => {
      try {
        const res = await fetchLayer({ key: layer.entry.key, bbox: bboxRef.current, time_index: 0 });
        return { ...layer, data: res.data, loading: false, error: undefined };
      } catch (err) {
        return { ...layer, data: null, loading: false, error: err instanceof Error ? err.message : "Failed to load layer." };
      }
    },
    []
  );

  const setBase = useCallback(
    (entry: MapCatalogEntry) => {
      const layer = makeLayer(entry, "base");
      setBaseRaw((prev) => {
        if (prev) pushRecent(prev.entry.key);
        return layer;
      });
      pushRecent(entry.key);
      fetchForLayer(layer).then(setBaseRaw);
    },
    [fetchForLayer, pushRecent]
  );

  const removeBase = useCallback(() => {
    setBaseRaw((prev) => {
      if (prev) pushRecent(prev.entry.key);
      return null;
    });
  }, [pushRecent]);

  const setBaseOpacity = useCallback((uid: string, opacity: number) => {
    setBaseRaw((prev) =>
      prev && prev.uid === uid ? { ...prev, opacity: Math.max(0, Math.min(1, opacity)) } : prev
    );
  }, []);

  const setBaseVisible = useCallback((uid: string, visible: boolean) => {
    setBaseRaw((prev) => (prev && prev.uid === uid ? { ...prev, visible } : prev));
  }, []);

  const toggleOverlay = useCallback(
    (entry: MapCatalogEntry) => {
      setOverlays((prev) => {
        const existing = prev.find((l) => l.entry.key === entry.key);
        if (existing) return prev.filter((l) => l.uid !== existing.uid);
        const layer = makeLayer(entry, "overlay");
        fetchForLayer(layer).then((loaded) =>
          setOverlays((cur) => cur.map((l) => (l.uid === loaded.uid ? loaded : l)))
        );
        return [...prev, layer];
      });
      pushRecent(entry.key);
    },
    [fetchForLayer, pushRecent]
  );
const removeOverlay = useCallback((uid: string) => {
    setOverlays((prev) => prev.filter((l) => l.uid !== uid));
  }, []);

  const moveOverlay = useCallback((uid: string, direction: -1 | 1) => {
    setOverlays((prev) => {
      const idx = prev.findIndex((l) => l.uid === uid);
      const target = idx + direction;
      if (idx < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      const [move] = next.splice(idx, 1);
      next.splice(target, 0, move);
      return next;
    });
  }, []);

  const setOverlayOpacity = useCallback((uid: string, opacity: number) => {
    setOverlays((prev) =>
      prev.map((l) => (l.uid === uid ? { ...l, opacity: Math.max(0.05, Math.min(1, opacity)) } : l))
    );
  }, []);

  const setOverlayVisible = useCallback((uid: string, visible: boolean) => {
    setOverlays((prev) => prev.map((l) => (l.uid === uid ? { ...l, visible } : l)));
  }, []);

  const setBbox = useCallback(
    (next: string) => {
      setBboxState(next);
      setOverlays((prev) => {
        for (const l of prev) {
          fetchForLayer({ ...l, loading: true }).then((loaded) =>
            setOverlays((cur) => cur.map((c) => (c.uid === loaded.uid ? loaded : c)))
          );
        }
        return prev.map((l) => ({ ...l, loading: true }));
      });
      if (base) {
        fetchForLayer({ ...base, loading: true }).then(setBaseRaw);
      }
    },
    [base, fetchForLayer]
  );

  const refreshData = useCallback(async () => {
    if (base) {
      const loaded = await fetchForLayer({ ...base, loading: true });
      setBaseRaw(loaded);
    }
    for (const layer of overlays) {
      const loaded = await fetchForLayer({ ...layer, loading: true });
      setOverlays((cur) => cur.map((l) => (l.uid === loaded.uid ? loaded : l)));
    }
  }, [base, overlays, fetchForLayer]);

  const recents = useMemo(
    () =>
      prefs.recents
        .map((key) => catalog?.entries.find((e) => e.key === key))
        .filter((e): e is MapCatalogEntry => Boolean(e)),
    [prefs.recents, catalog]
  );

  const favorites = useMemo(
    () =>
      prefs.favorites
        .map((key) => catalog?.entries.find((e) => e.key === key))
        .filter((e): e is MapCatalogEntry => Boolean(e)),
    [prefs.favorites, catalog]
  );

  const frames = Math.max(
    1,
    ...overlays.map((l) => l.data?.frames ?? TIME_FRAMES_DEFAULT).concat(base ? [base.data?.frames ?? TIME_FRAMES_DEFAULT] : [])
  );

  const model = useMapStyle({ base, overlays, timeIndex });

  const safeSetTimeIndex = useCallback((index: number) => {
    setTimeIndex(Math.max(0, index));
  }, []);

  return {
    base,
    overlays,
    recents,
    favorites,
    timeIndex,
    frames,
    model,
    setBase,
    toggleOverlay,
    removeOverlay,
    moveOverlay,
    setOverlayOpacity,
    setOverlayVisible,
    setBaseOpacity,
    setBaseVisible,
    setTimeIndex: safeSetTimeIndex,
    toggleFavorite,
    removeBase,
    setBbox,
    refreshData,
    catalog,
    loadCatalog,
  };
}