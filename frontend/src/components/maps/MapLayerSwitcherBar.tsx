/**
 * MapLayerSwitcherBar - floating quick-switch control bar for the main map
 * view: browse catalog, jump to recent/favorite map types, and toggle overlays.
 */
import { Clock, Library, Star } from "lucide-react";
import type { MapCatalogEntry } from "../../types/maps";

export interface MapLayerSwitcherBarProps {
  recents: MapCatalogEntry[];
  favorites: MapCatalogEntry[];
  overlays: MapCatalogEntry[];
  onOpenCatalog: () => void;
  onQuickSelect: (entry: MapCatalogEntry) => void;
  onToggleOverlay: (entry: MapCatalogEntry) => void;
}

export default function MapLayerSwitcherBar({
  recents,
  favorites,
  overlays,
  onOpenCatalog,
  onQuickSelect,
  onToggleOverlay,
}: MapLayerSwitcherBarProps) {
  const quick = [
    ...favorites.filter((e) => !recents.some((r) => r.key === e.key)),
    ...recents,
  ].slice(0, 6);

  return (
    <div className="pointer-events-auto absolute right-3 top-3 z-40 flex max-w-[70%] flex-wrap items-center gap-2 rounded-2xl border border-space-700 bg-space-900/90 px-3 py-2 shadow-2xl backdrop-blur-md">
      <button
        type="button"
        onClick={onOpenCatalog}
        className="btn-primary flex !h-9 items-center gap-1.5 !px-3 !py-1.5 text-xs"
      >
        <Library className="h-4 w-4" /> Catalog
      </button>

      {quick.map((entry) => (
        <button
          key={entry.key}
          type="button"
          title={entry.title}
          onClick={() => onQuickSelect(entry)}
          className="flex h-9 max-w-[150px] items-center gap-1.5 rounded-lg border border-space-600 bg-space-850 px-2.5 text-xs text-slate-300 transition hover:border-accent hover:text-accent"
        >
          {favorites.some((f) => f.key === entry.key) ? (
            <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-400" />
          ) : (
            <Clock className="h-3 w-3 shrink-0 text-slate-500" />
          )}
          <span className="truncate">{entry.title}</span>
        </button>
      ))}

      {overlays.length > 0 && (
        <>
          <span className="hidden h-5 w-px bg-space-600 sm:block" />
          <span className="hidden text-[10px] font-medium uppercase tracking-wider text-slate-500 sm:inline">
            {overlays.length} overlay{overlays.length === 1 ? "" : "s"}
          </span>
          {overlays.slice(0, 3).map((entry) => (
            <button
              key={entry.key}
              type="button"
              title={`Remove ${entry.title} overlay`}
              onClick={() => onToggleOverlay(entry)}
              className="flex h-9 items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-2.5 text-xs text-accent transition hover:bg-accent/20"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              {entry.title}
            </button>
          ))}
        </>
      )}
    </div>
  );
}