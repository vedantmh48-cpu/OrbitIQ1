/**
 * IdleSentry - global session guard.
 *
 * * Runs the client-side `useIdleTimer` whenever a user is signed in.
 * * Subscribes to `/ws/notifications/{user_id}` so a revoked session or a
 *   password change on another device signs this tab out immediately.
 * * Renders the non-dismissible auto-logout warning modal.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getAccessToken, getSessionId } from "../../api/client";
import { useIdleTimer } from "../../hooks/useIdleTimer";
import { computeIdleConfig } from "../../store/authStore";
import { useAuthStore } from "../../store/authStore";
import type { NotificationEvent } from "../../types/auth";
import AutoLogoutWarningModal from "./AutoLogoutWarningModal";

const WS_RECONNECT_MS = 5000;

export default function IdleSentry() {
  const user = useAuthStore(s => s.user);
  const booting = useAuthStore(s => s.booting);
  const logout = useAuthStore(s => s.logout);
  const [staying, setStaying] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const config = computeIdleConfig(user);
  const enabled = !!user && !booting;

  const { warning, secondsLeft, reset, staySignedIn } = useIdleTimer({
    enabled,
    timeoutMinutes: config.timeoutMinutes,
    warningLeadSeconds: config.warningLeadSeconds,
    onExpire: () => {
      /* logout handled inside the hook */
    },
  });

  // ---- WebSocket: immediate sign-out on session_revoked / password_changed ---
  useEffect(() => {
    const sessionId = getSessionId();
    if (!enabled || !user || !sessionId) return undefined;

    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const token = getAccessToken();
      if (!token) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(
        `${proto}://${window.location.host}/ws/notifications/${user.id}?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}`
      );
      wsRef.current = ws;

      ws.onmessage = event => {
        try {
          const msg = JSON.parse(event.data) as NotificationEvent;
          if (msg.type === "session_revoked") {
            if (msg.session_id === getSessionId() || msg.session_id === sessionId) {
              logout("revoked");
            }
          } else if (msg.type === "password_changed") {
            if (!msg.except_session_id || msg.except_session_id !== getSessionId()) {
              logout("password_changed");
            }
          } else if (msg.type === "account_deleted") {
            logout("revoked");
          }
        } catch {
          /* ignore malformed frame */
        }
      };

      ws.onclose = () => {
        if (disposed || !useAuthStore.getState().user) return;
        reconnectTimer.current = window.setTimeout(connect, WS_RECONNECT_MS);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [enabled, user?.id, logout]);

  const onStay = useCallback(async () => {
    setStaying(true);
    try {
      await staySignedIn();
    } finally {
      setStaying(false);
    }
  }, [staySignedIn]);

  return (
    <AutoLogoutWarningModal
      open={warning}
      secondsLeft={secondsLeft}
      timeoutMinutes={config.timeoutMinutes}
      governmentTier={config.governmentTier}
      staying={staying}
      onStay={onStay}
    />
  );
}