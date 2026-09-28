/* =========================================================================
   api.js — thin REST client for the Mission Control backend
   All calls hit the same origin (/api) so the console can be served by the
   FastAPI app itself, or via any reverse proxy.
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.api = (() => {
  async function request(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch("/api" + path, opts);
    } catch (err) {
      throw new Error("Mission Control API unreachable — is the backend running?");
    }
    if (res.status === 204) return null;
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* non-JSON body */
    }
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  return {
    health: () => request("GET", "/health"),
    overview: () => request("GET", "/overview"),

    missions: () => request("GET", "/missions"),
    createMission: (m) => request("POST", "/missions", m),
    updateMission: (id, patch) => request("PATCH", "/missions/" + id, patch),
    deleteMission: (id) => request("DELETE", "/missions/" + id),

    satellites: () => request("GET", "/satellites"),
    satellite: (id) => request("GET", "/satellites/" + id),

    telemetry: (id) => request("GET", "/telemetry/" + id),

    alerts: () => request("GET", "/alerts"),
    ackAlert: (id, ack) => request("PATCH", "/alerts/" + id, { acknowledged: ack }),
  };
})();