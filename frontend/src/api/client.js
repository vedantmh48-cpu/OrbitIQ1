const API_BASE = import.meta.env.VITE_API_BASE || "";

let accessToken = localStorage.getItem("satquery_access") || "";
let refreshToken = localStorage.getItem("satquery_refresh") || "";
let sessionId = localStorage.getItem("satquery_session") || "";

export function setTokens(access, refresh) {
  accessToken = access || "";
  refreshToken = refresh || "";
  if (accessToken) localStorage.setItem("satquery_access", accessToken);
  else localStorage.removeItem("satquery_access");
  if (refreshToken) localStorage.setItem("satquery_refresh", refreshToken);
  else localStorage.removeItem("satquery_refresh");
}

export function setSessionId(sid) {
  sessionId = sid || "";
  if (sessionId) localStorage.setItem("satquery_session", sessionId);
  else localStorage.removeItem("satquery_session");
}

export function getAccessToken() {
  return accessToken;
}

export function getRefreshToken() {
  return refreshToken;
}

export function getSessionId() {
  return sessionId;
}

export function getTokens() {
  return { accessToken, refreshToken, sessionId };
}

const REFRESH_ENDPOINT = () => (sessionId ? "/api/v1/auth/refresh" : "/api/auth/refresh");

async function request(path, { method = "GET", body, auth = true, raw = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  });

  // Single retry with a refreshed token on 401.
  if (res.status === 401 && auth && refreshToken && path !== REFRESH_ENDPOINT() && path !== "/api/v1/auth/refresh") {
    const ok = await tryRefresh();
    if (ok) {
      headers.Authorization = `Bearer ${accessToken}`;
      res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
      });
    }
  }

  // A 401 on an authenticated call means the session is genuinely gone. On an
  // unauthenticated call (login, OTP, password reset) it is a credential
  // failure, so fall through and surface the backend's own message + code.
  if (res.status === 401 && auth) {
    setTokens(null, null);
    setSessionId(null);
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }
  if (res.status === 429) {
    throw new ApiError("Too many requests — please wait a moment and try again.", 429);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let code;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
      code = data.code;
    } catch {
      /* keep default */
    }
    const err = new ApiError(detail, res.status, code);
    throw err;
  }
  return raw ? res : res.json();
}

export async function tryRefresh() {
  try {
    const data = await request(REFRESH_ENDPOINT(), {
      method: "POST",
      body: { refresh_token: refreshToken },
      auth: false
    });
    accessToken = data.access_token;
    if (data.session_id) {
      sessionId = data.session_id;
      localStorage.setItem("satquery_session", sessionId);
    } else {
      sessionId = "";
    }
    localStorage.setItem("satquery_access", accessToken);
    return true;
  } catch {
    setTokens(null, null);
    setSessionId(null);
    return false;
  }
}

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const api = {
  get: (p, o) => request(p, { ...o, method: "GET" }),
  post: (p, body, o) => request(p, { ...o, method: "POST", body }),
  put: (p, body, o) => request(p, { ...o, method: "PUT", body }),
  patch: (p, body, o) => request(p, { ...o, method: "PATCH", body }),
  del: (p, o) => request(p, { ...o, method: "DELETE" })
};

export function wsUrl(jobId) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const host = API_BASE ? new URL(API_BASE).host : location.host;
  return `${proto}://${host}/ws/jobs/${jobId}?token=${encodeURIComponent(accessToken)}`;
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export async function downloadFile(path, filename) {
  const res = await request(path, { auth: true, raw: true });
  downloadBlob(await res.blob(), filename);
}

export function formatNumber(n, digits = 0) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  });
}

export function formatPct(n) {
  if (n === null || n === undefined) return "—";
  return `${Math.round(Number(n) * 100)}%`;
}

export function formatDate(iso, withTime = true) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const parts = d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
    if (!withTime) return parts;
    return `${parts} · ${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
  } catch {
    return String(iso).replace("T", " ").slice(0, 16);
  }
}

export function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const secs = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/** Capitalise and pretty-print an operation id like "flood-mapping". */
export function prettyOp(op) {
  if (!op) return "Analysis";
  return String(op)
    .split("-")
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}