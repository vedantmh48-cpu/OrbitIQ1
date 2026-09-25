/**
 * TimeSliderControl - playback toolbar for temporal (time-series) map types.
 * Supports Play / Pause / Step and variable frame rates.
 */
import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { Button } from "../ui";

export interface TimeSliderControlProps {
  visible: boolean;
  frames: number;
  frame: number;
  playing: boolean;
  fps: number;
  onFrameChange: (frame: number) => void;
  onPlayingChange: (playing: boolean) => void;
  onFpsChange: (fps: number) => void;
}

const FPS_OPTIONS = [0.5, 1, 2, 4];

export default function TimeSliderControl({
  visible,
  frames,
  frame,
  playing,
  fps,
  onFrameChange,
  onPlayingChange,
  onFpsChange,
}: TimeSliderControlProps) {
  const timer = useRef<number | null>(null);
  const playingRef = useRef(playing);
  playingRef.current = playing;

  useEffect(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (!playing) return;
    timer.current = window.setInterval(() => {
      const next = (frame + 1) % Math.max(frames, 1);
      onFrameChange(next);
    }, Math.max(125, Math.round(1000 / fps)));
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing, fps, frame, frames, onFrameChange]);

  if (!visible || frames <= 1) return null;

  const step = (delta: number) => {
    const next = (frame + delta + frames) % frames;
    onFrameChange(next);
  };

  return (
    <div className="pointer-events-auto absolute bottom-5 left-1/2 z-40 flex w-[min(92%,560px)] -translate-x-1/2 items-center gap-3 rounded-2xl border border-space-700 bg-space-900/90 px-3 py-2 shadow-2xl backdrop-blur-md">
      <Button
        type="button"
        className="!px-2 !py-1.5"
        onClick={() => onPlayingChange(!playing)}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => step(-1)}
          className="rounded-lg p-1.5 text-slate-300 transition hover:bg-space-800 hover:text-accent"
          aria-label="Previous frame"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => step(1)}
          className="rounded-lg p-1.5 text-slate-300 transition hover:bg-space-800 hover:text-accent"
          aria-label="Next frame"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(frames - 1, 0)}
        value={frame}
        onChange={(e) => onFrameChange(Number(e.target.value))}
        className="h-1.5 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-space-700 accent-cyan-400"
        aria-label="Time frame"
      />

      <span className="shrink-0 font-mono text-xs tabular-nums text-slate-300">
        {String(frame + 1).padStart(2, "0")}
        <span className="text-slate-500"> / {String(frames).padStart(2, "0")}</span>
      </span>

      <select
        className="shrink-0 rounded-lg border border-space-700 bg-space-850 px-1.5 py-1 text-xs text-slate-300 outline-none focus:border-accent"
        value={fps}
        onChange={(e) => onFpsChange(Number(e.target.value))}
        aria-label="Frame rate"
      >
        {FPS_OPTIONS.map((f) => (
          <option key={f} value={f}>{f} fps</option>
        ))}
      </select>
    </div>
  );
}