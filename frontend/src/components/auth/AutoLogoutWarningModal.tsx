/**
 * Auto-logout warning modal.
 *
 * Non-dismissible: appears `timeout - 60s` before the idle deadline with a
 * live countdown. "Stay Signed In" calls `POST /api/v1/auth/heartbeat` to
 * reset the frontend timer and the server/Redis session timestamps.
 */
import { Clock, ShieldAlert } from "lucide-react";
import { Button } from "../ui";

export interface AutoLogoutWarningModalProps {
  open: boolean;
  secondsLeft: number;
  timeoutMinutes: number;
  governmentTier?: boolean;
  staying: boolean;
  onStay: () => void;
}

function fmt(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export default function AutoLogoutWarningModal({
  open,
  secondsLeft,
  timeoutMinutes,
  governmentTier = false,
  staying,
  onStay,
}: AutoLogoutWarningModalProps) {
  if (!open) return null;
  const progress = Math.min(100, (secondsLeft / 60) * 100);

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-space-950/70 px-4 backdrop-blur-sm">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label="Inactivity warning"
        className="card w-full max-w-md p-6"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-400">
            <ShieldAlert className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-white">You’re about to be signed out</h2>
            <p className="mt-1 text-sm text-slate-400">
              For your security, session{" "}
              <span className="font-medium text-slate-200">
                {timeoutMinutes} min{timeoutMinutes === 1 ? "" : "s"}
              </span>{" "}
              {governmentTier && (
                <>
                  (clamped to the organization maximum — no “Never” option)
                </>
              )}{" "}
              of inactivity ends automatically.
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-space-700 bg-space-850/60 p-4 text-center">
          <div className="font-mono text-4xl font-bold tabular-nums text-accent">{fmt(secondsLeft)}</div>
          <div className="mt-1 text-xs font-medium uppercase tracking-wider text-slate-400">
            until auto sign-out
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-space-700">
            <div
              className="h-full rounded-full bg-accent transition-all duration-1000 ease-linear"
              style={{ width: `${Math.max(0, progress)}%` }}
            />
          </div>
        </div>

        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          This window cannot be dismissed. Any mouse, keyboard, click, scroll or
          touch activity keeps your session alive.
        </p>

        <Button className="mt-5 w-full" loading={staying} onClick={onStay}>
          <Clock className="mr-2 h-4 w-4" />
          Stay signed in
        </Button>
      </div>
    </div>
  );
}