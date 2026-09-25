/**
 * LegendPanel - automatically renders the correct legend for each active map
 * layer: continuous gradient (heat / isarithmic / elevation), discrete classes
 * (choropleth / biomes / zoning), contour levels (topo / bathymetric) and
 * symbol scales (dot / proportional symbol).
 */
import type { LegendSpec } from "../../types/maps";

export default function LegendPanel({ legends }: { legends: LegendSpec[] }) {
  const visible = legends.filter((l) => (l.items?.length ?? 0) + (l.levels?.length ?? 0) + (l.stops?.length ?? 0) + (l.scale?.length ?? 0) > 0);
  if (visible.length === 0) return null;

  return (
    <div className="pointer-events-none absolute bottom-5 left-4 z-40 max-h-[60%] w-56 overflow-hidden rounded-xl border border-space-700 bg-space-900/90 px-3 py-2.5 backdrop-blur-md shadow-2xl">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        Legend
      </div>
      <div className="mt-1.5 space-y-3">
        {visible.map((legend, i) => (
          <div key={`${legend.type}-${i}`} className="min-w-0">
            <div className="truncate text-[10px] font-medium text-slate-300">{legend.label}</div>
            {legend.type === "gradient" && legend.stops && (
              <div className="mt-1">
                <div
                  className="h-2.5 w-full rounded-full"
                  style={{ background: `linear-gradient(90deg, ${legend.stops.map((s) => s.color).join(", ")})` }}
                />
                <div className="mt-1 flex justify-between gap-1 text-[9px] leading-none text-slate-500">
                  {legend.stops.map((s) => (
                    <span key={s.value} className="truncate px-0.5">{s.label || s.value}</span>
                  ))}
                </div>
              </div>
            )}
            {legend.type === "classes" && legend.items && (
              <ul className="mt-1 space-y-1">
                {legend.items.map((item) => (
                  <li key={item.label} className="flex items-center gap-2 text-[10px] text-slate-300">
                    <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: item.color }} />
                    <span className="truncate">{item.label}</span>
                  </li>
                ))}
              </ul>
            )}
            {legend.type === "contour" && legend.levels && (
              <ul className="mt-1 space-y-1">
                {legend.levels.map((lvl) => (
                  <li key={lvl.level} className="flex items-center gap-2 text-[10px] text-slate-300">
                    <span className="h-0.5 w-4 border-t-2" style={{ borderColor: lvl.color }} />
                    <span>{lvl.level}{legend.unit ? ` ${legend.unit}` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
            {legend.type === "symbol" && legend.scale && (
              <div className="mt-1 flex items-end justify-around gap-3">
                {legend.scale.map((entry) => (
                  <div key={entry.value} className="flex flex-col items-center">
                    <span
                      className="rounded-full border border-white/70"
                      style={{ width: entry.size * 2, height: entry.size * 2, background: "rgba(34,211,238,0.45)" }}
                    />
                    <span className="mt-0.5 text-[9px] text-slate-500">{entry.label || entry.value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}