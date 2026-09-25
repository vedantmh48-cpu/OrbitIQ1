/**
 * Active Sessions & Devices card.
 * Lists live sessions (device, IP, last activity) and allows revoking an
 * individual session or every other session.
 */
import { useCallback, useEffect, useState } from "react";
import { Laptop, MonitorSmartphone, RefreshCw, ShieldX } from "lucide-react";
import * as authApi from "../../api/auth";
import { timeAgo } from "../../api/client";
import type { Session } from "../../types/auth";
import { Badge, Button, Card, EmptyState, Spinner } from "../ui";

export default function ActiveSessionsCard() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revoking, setRevoking] = useState<string>("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await authApi.listSessions();
      setSessions(res.sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sessions.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const revokeOne = async (sessionId: string) => {
    setRevoking(sessionId);
    try {
      await authApi.revokeSession(sessionId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke session.");
    } finally {
      setRevoking("");
    }
  };

  const revokeAll = async () => {
    setBusy(true);
    try {
      const res = await authApi.revokeAllSessions();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign out other sessions.");
    } finally {
      setBusy(false);
    }
  };

  const current = sessions?.find(s => s.current);

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Active sessions & devices</h2>
          <p className="mt-0.5 text-sm text-slate-400">
            Devices currently signed in to your account.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-space-700 text-slate-400 transition hover:text-accent"
          aria-label="Refresh sessions"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}

      <div className="mt-4 space-y-3">
        {sessions === null ? (
          <div className="flex justify-center py-8">
            <Spinner label="Loading sessions…" />
          </div>
        ) : sessions.length === 0 ? (
          <EmptyState
            icon={<MonitorSmartphone className="h-7 w-7" />}
            title="No active sessions"
            message="Sessions you create will appear here."
          />
        ) : (
          sessions.map(s => (
            <div
              key={s.session_id}
              className="flex items-center justify-between gap-3 rounded-xl border border-space-700 bg-space-850/50 px-4 py-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-space-700 bg-space-800/60 text-slate-300">
                  <Laptop className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-slate-100">
                      {s.device_label || "Unknown device"}
                    </span>
                    {s.current && <Badge color="accent">This device</Badge>}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-500">
                    {s.ip_address || "—"} · last active {timeAgo(s.last_seen_at)}
                  </div>
                </div>
              </div>
              {!s.current && (
                <Button
                  variant="ghost"
                  className="shrink-0 text-xs"
                  loading={revoking === s.session_id}
                  onClick={() => revokeOne(s.session_id)}
                >
                  Sign out
                </Button>
              )}
            </div>
          ))
        )}
      </div>

      {sessions && sessions.length > 1 && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3">
          <div className="text-xs text-slate-400">
            End every other session. Your current device stays signed in.
          </div>
          <Button variant="danger" loading={busy} onClick={revokeAll} className="shrink-0 text-xs">
            <ShieldX className="mr-1.5 h-4 w-4" /> Sign out all other sessions
          </Button>
        </div>
      )}

      {current && (
        <p className="mt-4 text-xs text-slate-500">
          Session started {timeAgo(current.created_at)} · expires {timeAgo(current.expires_at)}.
        </p>
      )}
    </Card>
  );
}