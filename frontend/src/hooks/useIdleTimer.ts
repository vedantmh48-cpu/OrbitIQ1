/**
 * useIdleTimer - client-side inactivity auto-logout.
 *
 * * Tracks `mousemove`, `keydown`, `click`, `scroll`, `touchstart`
 *   (throttled to at most one update per `throttleMs`, default 5s).
 * * Shows a (non-dismissible) warning `warningLeadSeconds` before the
 *   configured `timeoutMinutes` deadline.
 * * "Stay Signed In" calls `POST /api/v1/auth/heartbeat` (resets both the
 *   frontend timer and the server/Redis `last_seen_at`).
 * * Once the deadline passes the caller is routed to sign-in.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "../store/authStore";
import type { SessionRevokedReason } from "../types/auth";

export interface UseIdleTimerOptions {
  enabled: boolean;
  timeoutMinutes: number;
  warningLeadSeconds?: number;
  throttleMs?: number;
  onExpire?: (reason: SessionRevokedReason) => void;
}

const ACTIVITY_EVENTS = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;

export function useIdleTimer({
  enabled,
  timeoutMinutes,
  warningLeadSeconds = 60,
  throttleMs = 5000,
  onExpire,
}: UseIdleTimerOptions) {
  const lastActivity = useRef<number>(Date.now());
  const lastEmit = useRef<number>(0);
  const heartbeat = useAuthStore((s) => s.heartbeat);
  const logout = useAuthStore((s) => s.logout);
  const [warning, setWarning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const expiredRef = useRef(false);
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  const timeoutMs = Math.max(timeoutMinutes, 1) * 60_000;

  const reset = useCallback(() => {
    lastActivity.current = Date.now();
    expiredRef.current = false;
    setWarning(false);
    setSecondsLeft(0);
  }, []);

  /** Throttled event handler: refresh the idle clock at most every 5s. */
  const handleActivity = useCallback(() => {
    if (!enabled) return;
    const now = Date.now();
    if (now - lastEmit.current < throttleMs) return;
    lastEmit.current = now;
    lastActivity.current = now;
    setWarning(false);
  }, [enabled, throttleMs]);

  useEffect(() => {
    if (!enabled) return undefined;
    const handler = () => handleActivity();
    for (const evt of ACTIVITY_EVENTS) {
      window.addEventListener(evt, handler, { passive: true } as AddEventListenerOptions);
    }
    const onVisible = () => {
      // Returning to the tab counts as activity.
      if (!document.hidden) handler();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      for (const evt of ACTIVITY_EVENTS) {
        window.removeEventListener(evt, handler);
      }
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [enabled, handleActivity]);

  useEffect(() => {
    if (!enabled) {
      setWarning(false);
      return undefined;
    }
    const tick = () => {
      const elapsed = Date.now() - lastActivity.current;
      if (expiredRef.current) return;
      if (elapsed >= timeoutMs) {
        expiredRef.current = true;
        setWarning(false);
        logout("inactive");
        onExpireRef.current?.("inactive");
        return;
      }
      const remainingMs = timeoutMs - elapsed;
      const leadMs = warningLeadSeconds * 1000;
      if (!warning && remainingMs <= leadMs) {
        setWarning(true);
        setSecondsLeft(Math.ceil(remainingMs / 1000));
        return;
      }
      if (warning) {
        setSecondsLeft(Math.max(0, Math.ceil(remainingMs / 1000)));
      }
    };
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [enabled, timeoutMs, warning, warningLeadSeconds, logout]);

  /** "Stay Signed In" -> heartbeat resets server + Redis + local timers. */
  const staySignedIn = useCallback(async () => {
    const ok = await heartbeat();
    if (ok) {
      reset();
      return true;
    }
    // Heartbeat failed: the session was already revoked server-side.
    logout("expired");
    return false;
  }, [heartbeat, reset, logout]);

  return { warning, secondsLeft, reset, staySignedIn, isActive: enabled };
}