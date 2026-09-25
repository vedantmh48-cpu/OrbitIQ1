import { Satellite } from "lucide-react";

export default function Logo({ size = 40, withText = true, className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div className="relative flex items-center justify-center">
        <div
          className="sat-orb rounded-full"
          style={{ width: size, height: size }}
        />
        <Satellite
          className="absolute text-space-950"
          style={{ width: size * 0.5, height: size * 0.5 }}
          strokeWidth={2.2}
        />
      </div>
      {withText && (
        <div className="leading-tight">
          <div className="font-extrabold tracking-tight text-white text-lg">
            Orbit<span className="text-accent">IQ</span>
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
            Satellite Intelligence
          </div>
        </div>
      )}
    </div>
  );
}