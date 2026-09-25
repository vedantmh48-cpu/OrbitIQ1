/**
 * MapTypeCatalogModal - categorized map selector with search, thumbnail
 * previews, favorites and base/overlay actions for all 30+ map types.
 */
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Globe2, Layers3, Search, Star, X } from "lucide-react";
import type { MapCatalogEntry, MapCategory } from "../../types/maps";
import type { CatalogCache } from "../../hooks/MapLayerController";
import { MAP_CATEGORY_LABELS, MAP_CATEGORY_ORDER } from "../../types/maps";
import { Badge, Button } from "../ui";

export interface MapTypeCatalogModalProps {
  open: boolean;
  onClose: () => void;
  catalog: CatalogCache | null;
  activeKeys: string[];
  favorites: string[];
  onSelectBase: (entry: MapCatalogEntry) => void;
  onToggleOverlay: (entry: MapCatalogEntry) => void;
  onToggleFavorite: (key: string) => void;
}

function thumbnailStyle(entry: MapCatalogEntry): CSSProperties {
  const legend = entry.legend;
  if (legend.type === "gradient" && legend.stops?.length) {
    return { background: `linear-gradient(135deg, ${legend.stops.map((s) => s.color).join(", ")})` };
  }
  if (legend.type === "classes" && legend.items?.length) {
    const colors = legend.items.map((i) => i.color);
    const segments = Math.min(colors.length, 4);
    const size = 100 / segments;
    return {
      background: `linear-gradient(135deg, ${colors
        .slice(0, segments)
        .map((c, i) => `${c} ${i * size}% ${(i + 1) * size}%`)
        .join(", ")})`,
    };
  }
  if (legend.type === "contour" && legend.levels?.length) {
    const colors = legend.levels.map((l) => l.color);
    return { background: `linear-gradient(135deg, ${colors.join(", ")})` };
  }
  return { background: "linear-gradient(135deg, #0ea5e9, #22d3ee, #8b5cf6)" };
}
export default function MapTypeCatalogModal({
  open,
  onClose,
  catalog,
  activeKeys,
  favorites,
  onSelectBase,
  onToggleOverlay,
  onToggleFavorite,
}: MapTypeCatalogModalProps) {
  const [category, setCategory] = useState<MapCategory | "all">("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    if (open) {
      setCategory("all");
      setQ("");
    }
  }, [open]);

  if (!open) return null;

  const entries = (catalog?.entries ?? []).filter((e) => {
    if (category !== "all" && e.category !== category) return false;
    const needle = q.trim().toLowerCase();
    if (needle) {
      return (
        e.title.toLowerCase().includes(needle) ||
        e.key.toLowerCase().includes(needle) ||
        e.summary.toLowerCase().includes(needle)
      );
    }
    return true;
  });

  const grouped = MAP_CATEGORY_ORDER.map((cat) => ({
    id: cat,
    label: MAP_CATEGORY_LABELS[cat],
    items: entries.filter((e) => e.category === cat),
  }));

  return (
    <div className="fixed inset-0 z-[85] flex overflow-y-auto bg-space-950/85 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-white">Map Type Catalog</h2>
            <p className="text-sm text-slate-400">
              {catalog?.entries.length ?? 0} cartographic types · pick a base map or stack an overlay.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-space-700 p-2.5 text-slate-400 transition hover:bg-space-800 hover:text-white"
            aria-label="Close catalog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            className="input h-9 w-64"
            placeholder="Search maps (heat, cadastre, DEM…)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="ml-1 h-8 w-px bg-space-700" />
          {(["all", ...MAP_CATEGORY_ORDER] as (MapCategory | "all")[]).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setCategory(cat)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                category === cat
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-space-600 text-slate-400 hover:border-space-500 hover:text-slate-200"
              }`}
            >
              {cat === "all" ? "All" : MAP_CATEGORY_LABELS[cat as MapCategory]}
            </button>
          ))}
        </div>
{grouped
          .filter((g) => g.items.length)
          .map((group) => (
            <section key={group.id}>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold capitalize text-accent">
                <span className="h-1.5 w-6 rounded-full bg-accent/60" />
                {group.label}
                <span className="text-xs text-slate-500">({group.items.length})</span>
              </h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.items.map((entry) => {
                  const active = activeKeys.includes(entry.key);
                  const fav = favorites.includes(entry.key);
                  return (
                    <div
                      key={entry.key}
                      className={`card group p-3 transition hover:-translate-y-0.5 hover:border-accent/60 ${
                        active ? "!border-accent/70" : ""
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="flex h-14 w-20 shrink-0 overflow-hidden rounded-lg border border-space-700">
                          <span className="h-full w-full" style={thumbnailStyle(entry)} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1">
                            <span className="truncate text-sm font-semibold text-slate-100">
                              {entry.is_3d_supported ? <Globe2 className="mr-1 inline h-3.5 w-3.5 text-accent" /> : null}
                              {entry.title}
                            </span>
                          </div>
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            <Badge color="slate">{entry.category.replace("_", " ")}</Badge>
                            {entry.is_temporal && <Badge color="accent">time-series</Badge>}
                            {entry.is_3d_supported && <Badge color="green">3D</Badge>}
                          </div>
                        </div>
                      </div>
                      <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-slate-400">
                        {entry.summary}
                      </p>
<div className="mt-2 flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => onToggleFavorite(entry.key)}
                          className={`flex h-8 w-8 items-center justify-center rounded-lg border transition ${
                            fav
                              ? "border-amber-500/50 bg-amber-500/10 text-amber-400"
                              : "border-space-700 text-slate-500 hover:text-amber-400"
                          }`}
                          aria-label="Toggle favorite"
                        >
                          <Star className={`h-4 w-4 ${fav ? "fill-amber-400" : ""}`} />
                        </button>
                        <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            className="!px-2.5 !py-1 text-xs"
                            onClick={() => onToggleOverlay(entry)}
                          >
                            <Layers3 className="mr-1 h-3.5 w-3.5" />
                            {active ? "Overlay on" : "Overlay"}
                          </Button>
                          <Button
                            className="!px-2.5 !py-1 text-xs"
                            onClick={() => {
                              onSelectBase(entry);
                              onClose();
                            }}
                          >
                            Base
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}

        {entries.length === 0 && (
          <div className="card flex flex-col items-center justify-center px-6 py-14 text-center">
            <Search className="mb-3 h-8 w-8 text-slate-500" />
            <h3 className="text-base font-semibold text-slate-200">No maps match “{q}”</h3>
            <p className="mt-1 text-sm text-slate-500">Try a different keyword or category.</p>
          </div>
        )}
      </div>
    </div>
  );
}