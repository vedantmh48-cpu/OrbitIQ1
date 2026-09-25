/**
 * LayerStackPanel - active layer stack with opacity, visibility and z-order
 * controls. Includes a base map row plus every stacked overlay.
 */
import { Eye, EyeOff, Layers3, MoveDown, MoveUp, X } from "lucide-react";
import type { ActiveMapLayer } from "../../types/maps";

export interface LayerStackPanelProps {
  base: ActiveMapLayer | null;
  overlays: ActiveMapLayer[];
  onRemoveBase: () => void;
  onRemoveOverlay: (uid: string) => void;
  onMoveOverlay: (uid: string, direction: -1 | 1) => void;
  onSetOpacity: (uid: string, opacity: number) => void;
  onSetVisible: (uid: string, visible: boolean) => void;
  onSetBaseOpacity: (uid: string, opacity: number) => void;
}

function LayerRow({
  layer,
  isBase,
  onRemove,
  onMove,
  onOpacity,
  onVisible,
}: {
  layer: ActiveMapLayer;
  isBase: boolean;
  onRemove: () => void;
  onMove: ((dir: -1 | 1) => void) | null;
  onOpacity: (value: number) => void;
  onVisible: (value: boolean) => void;
}) {
  return (
    <div className={`flex flex-col gap-2 rounded-xl border px-3 py-2 ${isBase ? "border-accent/40 bg-accent/5" : "border-space-700 bg-space-850/60"}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {!isBase && (
            <button
              type="button"
              onClick={() => onVisible(!layer.visible)}
              className="shrink-0 text-slate-400 transition hover:text-accent"
              aria-label="Toggle visibility"
            >
              {layer.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4 text-slate-600" />}
            </button>
          )}
          <span className={`truncate text-xs font-medium ${layer.visible ? "text-slate-100" : "text-slate-500"}`}>
            {isBase ? "Base: " : ""}
            {layer.entry.title}
          </span>
          {layer.loading && <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent" />}
          {layer.error && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-400" title={layer.error} />}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          {onMove && (
            <>
              <button type="button" className="p-1 text-slate-500 transition hover:text-accent" onClick={() => onMove(1)} aria-label="Move up">
                <MoveUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" className="p-1 text-slate-500 transition hover:text-accent" onClick={() => onMove(-1)} aria-label="Move down">
                <MoveDown className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          <button type="button" className="p-1 text-slate-500 transition hover:text-rose-400" onClick={onRemove} aria-label="Remove layer">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <label className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-slate-500">Opacity</span>
        <input
          type="range"
          min={0.05}
          max={1}
          step={0.05}
          value={layer.opacity}
          disabled={!layer.visible}
          onChange={(e) => onOpacity(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-space-700 accent-cyan-400"
        />
        <span className="text-[10px] tabular-nums text-slate-500">{Math.round(layer.opacity * 100)}%</span>
      </label>
    </div>
  );
}

export default function LayerStackPanel({
  base,
  overlays,
  onRemoveBase,
  onRemoveOverlay,
  onMoveOverlay,
  onSetOpacity,
  onSetVisible,
  onSetBaseOpacity,
}: LayerStackPanelProps) {
  return (
    <div className="pointer-events-auto absolute bottom-5 right-3 z-40 w-64 space-y-2 rounded-2xl border border-space-700 bg-space-900/90 p-3 shadow-2xl backdrop-blur-md">
      <div className="flex items-center gap-2">
        <Layers3 className="h-4 w-4 text-accent" />
        <span className="text-xs font-semibold text-white">Layer stack</span>
        <span className="ml-auto text-[10px] text-slate-500">{base ? 1 + overlays.length : overlays.length}</span>
      </div>
      {!base && overlays.length === 0 && (
        <p className="text-[11px] leading-relaxed text-slate-500">
          No layers yet. Open the catalog and choose a base map.
        </p>
      )}
      {base && (
        <LayerRow
          key={base.uid}
          layer={base}
          isBase
          onRemove={onRemoveBase}
          onMove={null}
          onOpacity={(v) => onSetBaseOpacity(base.uid, v)}
          onVisible={() => undefined}
        />
      )}
      {overlays.map((layer) => (
        <LayerRow
          key={layer.uid}
          layer={layer}
          isBase={false}
          onRemove={() => onRemoveOverlay(layer.uid)}
          onMove={(dir) => onMoveOverlay(layer.uid, dir)}
          onOpacity={(v) => onSetOpacity(layer.uid, v)}
          onVisible={(v) => onSetVisible(layer.uid, v)}
        />
      ))}
    </div>
  );
}