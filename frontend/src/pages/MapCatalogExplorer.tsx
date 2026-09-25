/**
 * MapCatalogExplorer - the interactive map-type workspace.
 *
 * Brings together the catalog modal, quick-switch bar, layer stack controls,
 * dynamic legend, time-series playback and the MapLibre + Deck.gl canvas.
 */
import { useEffect, useState } from "react";
import { Layers3, Map as MapIcon, RefreshCw } from "lucide-react";
import { MapLayerController } from "../hooks/MapLayerController";
import MapExplorerCanvas from "../components/maps/MapExplorerCanvas";
import MapLayerSwitcherBar from "../components/maps/MapLayerSwitcherBar";
import LayerStackPanel from "../components/maps/LayerStackPanel";
import LegendPanel from "../components/maps/LegendPanel";
import TimeSliderControl from "../components/maps/TimeSliderControl";
import MapTypeCatalogModal from "../components/maps/MapTypeCatalogModal";
import { Badge } from "../components/ui";

export default function MapCatalogExplorer() {
  const ctl = MapLayerController();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(1);

  useEffect(() => {
    if (ctl.frames <= 1) setPlaying(false);
  }, [ctl.frames]);

  const activeKeys = [
    ctl.base?.entry.key ?? null,
    ...ctl.overlays.filter((o) => o.visible).map((o) => o.entry.key),
  ].filter(Boolean) as string[];

  const overlayEntries = ctl.overlays.filter((o) => o.visible).map((o) => o.entry);
  const deckOverlayCount = ctl.overlays.filter((o) => o.visible && o.data).length;

  return (
    <div className="relative h-[calc(100dvh-3.5rem)] overflow-hidden rounded-xl border border-space-700 bg-space-950">
      <MapExplorerCanvas
        model={ctl.model}
        baseUid={ctl.base?.uid ?? null}
        deckLayers={ctl.model.deckLayers}
      />

      {/* Active map info chip */}
      <div className="pointer-events-auto absolute left-3 top-3 z-40 flex max-w-[220px] flex-col gap-1 rounded-2xl border border-space-700 bg-space-900/90 px-3 py-2 shadow-2xl backdrop-blur-md">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
          <MapIcon className="h-3.5 w-3.5 text-accent" />
          <span className="truncate">{ctl.base?.entry.title ?? "No base map"}</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {ctl.base && <Badge color="accent">{ctl.base.entry.engine}</Badge>}
          {deckOverlayCount > 0 && <Badge color="slate">{deckOverlayCount} deck overlay{deckOverlayCount === 1 ? "" : "s"}</Badge>}
          {ctl.model.demSourceId && <Badge color="green">terrain</Badge>}
        </div>
        <button
          type="button"
          onClick={() => ctl.refreshData()}
          className="mt-0.5 inline-flex w-fit items-center gap-1 text-[10px] text-slate-400 transition hover:text-accent"
        >
          <RefreshCw className="h-3 w-3" /> Regenerate demo data
        </button>
      </div>

      <MapLayerSwitcherBar
        recents={ctl.recents}
        favorites={ctl.favorites}
        overlays={overlayEntries}
        onOpenCatalog={() => setCatalogOpen(true)}
        onQuickSelect={ctl.setBase}
        onToggleOverlay={ctl.toggleOverlay}
      />

      <LayerStackPanel
        base={ctl.base}
        overlays={ctl.overlays}
        onRemoveBase={ctl.removeBase}
        onRemoveOverlay={ctl.removeOverlay}
        onMoveOverlay={ctl.moveOverlay}
        onSetOpacity={ctl.setOverlayOpacity}
        onSetVisible={ctl.setOverlayVisible}
        onSetBaseOpacity={ctl.setBaseOpacity}
      />

      <LegendPanel legends={ctl.model.legends} />

      <TimeSliderControl
        visible={ctl.model.temporal && ctl.frames > 1}
        frames={ctl.frames}
        frame={ctl.timeIndex}
        playing={playing}
        fps={fps}
        onFrameChange={ctl.setTimeIndex}
        onPlayingChange={setPlaying}
        onFpsChange={setFps}
      />

      {/* empty-state hint */}
      {!ctl.base && ctl.overlays.length === 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-24 z-30 mx-auto w-fit max-w-md rounded-2xl border border-space-700 bg-space-900/80 px-5 py-3 text-center backdrop-blur-md">
          <Layers3 className="mx-auto mb-1 h-5 w-5 text-accent" />
          <p className="text-sm text-slate-300">
            Open the <span className="font-semibold text-accent">Map Type Catalog</span> to pick a base map,
            then stack thematic overlays — choropleths, isolines, flows, heat maps, cadastre and 3D terrain.
          </p>
        </div>
      )}

      <MapTypeCatalogModal
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        catalog={ctl.catalog}
        activeKeys={activeKeys}
        favorites={ctl.favorites.map((f) => f.key)}
        onSelectBase={ctl.setBase}
        onToggleOverlay={ctl.toggleOverlay}
        onToggleFavorite={ctl.toggleFavorite}
      />
    </div>
  );
}