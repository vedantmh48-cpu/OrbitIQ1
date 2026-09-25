var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __esm = (fn, res) => function __init() {
  return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// <define:import.meta.env>
var define_import_meta_env_default;
var init_define_import_meta_env = __esm({
  "<define:import.meta.env>"() {
    define_import_meta_env_default = {};
  }
});

// .smoke/zustand-shim.mjs
import { createStore } from "zustand/vanilla";
import { useStore } from "zustand/react";
function setStateOverride(fn) {
  override = fn;
}
function create(createState) {
  const api2 = createStore(createState);
  const base = api2.getInitialState;
  api2.getInitialState = () => {
    const initial = base();
    return override ? { ...initial, ...override(initial) } : initial;
  };
  const useBoundStore = (selector) => useStore(api2, selector);
  Object.assign(useBoundStore, api2);
  return useBoundStore;
}
var override;
var init_zustand_shim = __esm({
  ".smoke/zustand-shim.mjs"() {
    "use strict";
    init_define_import_meta_env();
    override = null;
  }
});

// src/api/client.js
var client_exports = {};
__export(client_exports, {
  ApiError: () => ApiError,
  api: () => api,
  downloadBlob: () => downloadBlob,
  downloadFile: () => downloadFile,
  formatDate: () => formatDate,
  formatNumber: () => formatNumber,
  formatPct: () => formatPct,
  getAccessToken: () => getAccessToken,
  getRefreshToken: () => getRefreshToken,
  getSessionId: () => getSessionId,
  getTokens: () => getTokens,
  prettyOp: () => prettyOp,
  setSessionId: () => setSessionId,
  setTokens: () => setTokens,
  timeAgo: () => timeAgo,
  tryRefresh: () => tryRefresh,
  wsUrl: () => wsUrl
});
function setTokens(access, refresh) {
  accessToken = access || "";
  refreshToken = refresh || "";
  if (accessToken) localStorage.setItem("satquery_access", accessToken);
  else localStorage.removeItem("satquery_access");
  if (refreshToken) localStorage.setItem("satquery_refresh", refreshToken);
  else localStorage.removeItem("satquery_refresh");
}
function setSessionId(sid) {
  sessionId = sid || "";
  if (sessionId) localStorage.setItem("satquery_session", sessionId);
  else localStorage.removeItem("satquery_session");
}
function getAccessToken() {
  return accessToken;
}
function getRefreshToken() {
  return refreshToken;
}
function getSessionId() {
  return sessionId;
}
function getTokens() {
  return { accessToken, refreshToken, sessionId };
}
async function request(path, { method = "GET", body, auth = true, raw = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : void 0
  });
  if (res.status === 401 && auth && refreshToken && path !== REFRESH_ENDPOINT() && path !== "/api/v1/auth/refresh") {
    const ok = await tryRefresh();
    if (ok) {
      headers.Authorization = `Bearer ${accessToken}`;
      res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : void 0
      });
    }
  }
  if (res.status === 401 && auth) {
    setTokens(null, null);
    setSessionId(null);
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }
  if (res.status === 429) {
    throw new ApiError("Too many requests \u2014 please wait a moment and try again.", 429);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let code;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
      code = data.code;
    } catch {
    }
    const err = new ApiError(detail, res.status, code);
    throw err;
  }
  return raw ? res : res.json();
}
async function tryRefresh() {
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
function wsUrl(jobId) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const host = API_BASE ? new URL(API_BASE).host : location.host;
  return `${proto}://${host}/ws/jobs/${jobId}?token=${encodeURIComponent(accessToken)}`;
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2e3);
}
async function downloadFile(path, filename) {
  const res = await request(path, { auth: true, raw: true });
  downloadBlob(await res.blob(), filename);
}
function formatNumber(n, digits = 0) {
  if (n === null || n === void 0) return "\u2014";
  return Number(n).toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  });
}
function formatPct(n) {
  if (n === null || n === void 0) return "\u2014";
  return `${Math.round(Number(n) * 100)}%`;
}
function formatDate(iso, withTime = true) {
  if (!iso) return "\u2014";
  try {
    const d = new Date(iso);
    const parts = d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
    if (!withTime) return parts;
    return `${parts} \xB7 ${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
  } catch {
    return String(iso).replace("T", " ").slice(0, 16);
  }
}
function timeAgo(iso) {
  if (!iso) return "\u2014";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "\u2014";
  const secs = Math.max(1, Math.floor((Date.now() - then) / 1e3));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
function prettyOp(op) {
  if (!op) return "Analysis";
  return String(op).split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}
var API_BASE, accessToken, refreshToken, sessionId, REFRESH_ENDPOINT, ApiError, api;
var init_client = __esm({
  "src/api/client.js"() {
    "use strict";
    init_define_import_meta_env();
    API_BASE = define_import_meta_env_default.VITE_API_BASE || "";
    accessToken = localStorage.getItem("satquery_access") || "";
    refreshToken = localStorage.getItem("satquery_refresh") || "";
    sessionId = localStorage.getItem("satquery_session") || "";
    REFRESH_ENDPOINT = () => sessionId ? "/api/v1/auth/refresh" : "/api/auth/refresh";
    ApiError = class extends Error {
      constructor(message, status, code) {
        super(message);
        this.status = status;
        this.code = code;
      }
    };
    api = {
      get: (p, o) => request(p, { ...o, method: "GET" }),
      post: (p, body, o) => request(p, { ...o, method: "POST", body }),
      put: (p, body, o) => request(p, { ...o, method: "PUT", body }),
      patch: (p, body, o) => request(p, { ...o, method: "PATCH", body }),
      del: (p, o) => request(p, { ...o, method: "DELETE" })
    };
  }
});

// src/api/auth.ts
async function register(params) {
  return api.post(`${AUTH}/register`, params, { auth: false });
}
async function verifyEmail(email, code) {
  return api.post(`${AUTH}/verify-email`, { email, code }, { auth: false });
}
async function resendVerification(email) {
  return api.post(`${AUTH}/verify-email/resend`, { email }, { auth: false });
}
async function login(params) {
  return api.post(`${AUTH}/login`, params, { auth: false });
}
async function mfaChallenge(params) {
  return api.post(`${AUTH}/mfa/challenge`, params, { auth: false });
}
async function apiGetMe() {
  return api.get("/api/users/me");
}
async function logout(refreshToken2) {
  return api.post(`${AUTH}/logout`, { refresh_token: refreshToken2 }, { auth: true });
}
async function heartbeat() {
  return api.post(`${AUTH}/heartbeat`, {}, { auth: true });
}
async function mfaSetup() {
  return api.post(`${AUTH}/mfa/setup`);
}
async function mfaVerify(params) {
  return api.post(`${AUTH}/mfa/verify`, params);
}
var AUTH, AuthStepRequired;
var init_auth = __esm({
  "src/api/auth.ts"() {
    "use strict";
    init_define_import_meta_env();
    init_client();
    AUTH = "/api/v1/auth";
    AuthStepRequired = class extends Error {
      body;
      constructor(body) {
        super("Additional authentication step required.");
        this.body = body;
      }
    };
  }
});

// src/store/authStore.ts
var authStore_exports = {};
__export(authStore_exports, {
  computeIdleConfig: () => computeIdleConfig,
  getAuthSnapshot: () => getAuthSnapshot,
  useAuthStore: () => useAuthStore
});
function isGovOrg(user) {
  return !!user && user.account_type === "organization" && (user.org_type === "government" || user.org_type === "defense");
}
function loadStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}
function persistUser(user) {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  else localStorage.removeItem(USER_KEY);
}
function computeIdleConfig(user) {
  const gov = isGovOrg(user);
  const selectable = gov ? ALL_OPTIONS.filter((o) => o <= 15) : [...ALL_OPTIONS];
  return {
    timeoutMinutes: user?.inactivity_timeout_minutes ?? 15,
    warningLeadSeconds: 60,
    maxTimeoutMinutes: gov ? 15 : 60,
    governmentTier: gov,
    selectableOptions: selectable
  };
}
function applySession(user, tokens2) {
  setTokens(tokens2.access_token, tokens2.refresh_token);
  setSessionId(tokens2.session_id);
  persistUser(user);
}
function getAuthSnapshot() {
  return useAuthStore.getState();
}
var USER_KEY, ALL_OPTIONS, useAuthStore;
var init_authStore = __esm({
  "src/store/authStore.ts"() {
    "use strict";
    init_define_import_meta_env();
    init_zustand_shim();
    init_client();
    init_auth();
    USER_KEY = "satquery_user";
    ALL_OPTIONS = [5, 15, 30, 60];
    useAuthStore = create((set) => ({
      user: loadStoredUser(),
      loading: false,
      booting: true,
      pendingVerification: null,
      mfaStep: null,
      hydrate: async () => {
        const existing = useAuthStore.getState().user;
        if (!existing) {
          set({ loading: false, booting: false });
          return;
        }
        try {
          const me = await apiGetMe();
          persistUser(me);
          set({ user: me, loading: false, booting: false });
        } catch {
          setTokens(null, null);
          setSessionId(null);
          persistUser(null);
          set({ user: null, loading: false, booting: false });
        }
      },
      register: async (payload) => {
        set({ loading: true });
        try {
          const res = await register(payload);
          set({ pendingVerification: { email: res.email } });
          return { user: res.user, demoCode: res.demo_code };
        } finally {
          set({ loading: false });
        }
      },
      resendVerification: async (email) => {
        const res = await resendVerification(email);
        return res.demo_code;
      },
      verifyEmail: async (email, code) => {
        set({ loading: true });
        try {
          const res = await verifyEmail(email, code);
          applySession(res.user, res);
          set({ user: res.user, pendingVerification: null, loading: false, booting: false });
          return res.user;
        } catch (err) {
          set({ loading: false });
          throw err;
        }
      },
      login: async (params) => {
        set({ loading: true });
        try {
          const res = await login(params);
          if ("mfa_required" in res && res.mfa_required) {
            set({ mfaStep: { mfaToken: res.mfa_token, email: res.email, setupRequired: false } });
            throw new AuthStepRequired(res);
          }
          if ("mfa_setup_required" in res && res.mfa_setup_required) {
            set({
              mfaStep: { mfaToken: res.mfa_token, email: res.email, setupRequired: true },
              user: res.user
            });
            throw new AuthStepRequired(res);
          }
          if (!("mfa_required" in res) && !("mfa_setup_required" in res)) {
            applySession(res.user, {
              access_token: res.access_token,
              refresh_token: res.refresh_token,
              session_id: res.session_id
            });
            set({ user: res.user, mfaStep: null, loading: false });
            return res.user;
          }
          throw new Error("Unexpected login response shape.");
        } catch (err) {
          set({ loading: false });
          throw err;
        }
      },
      completeMfa: async (mfaToken, code) => {
        set({ loading: true });
        try {
          const res = await mfaChallenge({ mfa_token: mfaToken, code });
          applySession(res.user, res);
          set({ user: res.user, mfaStep: null, loading: false });
          return res.user;
        } catch (err) {
          set({ loading: false });
          throw err;
        }
      },
      logout: async (reason) => {
        const { refreshToken: refreshToken2 } = getTokens();
        try {
          if (refreshToken2) await logout(refreshToken2);
        } catch {
        }
        setTokens(null, null);
        setSessionId(null);
        persistUser(null);
        set({ user: null, mfaStep: null, loading: false, pendingVerification: null });
        const from = reason ? `?reason=${encodeURIComponent(reason)}` : "";
        if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
          window.location.href = `/login${from}`;
        }
      },
      heartbeat: async () => {
        try {
          await heartbeat();
          return true;
        } catch {
          return false;
        }
      },
      refreshUser: async () => {
        const me = await apiGetMe();
        persistUser(me);
        set({ user: me });
        return me;
      },
      setMfaStep: (step) => set({ mfaStep: step }),
      clearPendingVerification: () => set({ pendingVerification: null })
    }));
  }
});

// src/context/AuthContext.jsx
var AuthContext_exports = {};
__export(AuthContext_exports, {
  AuthProvider: () => AuthProvider,
  useAuth: () => useAuth
});
import { createContext, useContext, useEffect, useMemo } from "react";
import { jsx } from "react/jsx-runtime";
function AuthProvider({ children }) {
  const user = useAuthStore((s) => s.user);
  const loading = useAuthStore((s) => s.loading);
  const booting = useAuthStore((s) => s.booting);
  const login2 = useAuthStore((s) => s.login);
  const register2 = useAuthStore((s) => s.register);
  const logout2 = useAuthStore((s) => s.logout);
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => {
    hydrate();
  }, [hydrate]);
  const value = useMemo(
    () => ({ user, login: login2, register: register2, logout: logout2, refreshUser, loading, booting }),
    [user, login2, register2, logout2, refreshUser, loading, booting]
  );
  return /* @__PURE__ */ jsx(AuthContext.Provider, { value, children });
}
function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
var AuthContext;
var init_AuthContext = __esm({
  "src/context/AuthContext.jsx"() {
    "use strict";
    init_define_import_meta_env();
    init_authStore();
    AuthContext = createContext(null);
  }
});

// src/components/Logo.jsx
import { Satellite } from "lucide-react";
import { jsx as jsx2, jsxs } from "react/jsx-runtime";
function Logo({ size = 40, withText = true, className = "" }) {
  return /* @__PURE__ */ jsxs("div", { className: `flex items-center gap-2.5 ${className}`, children: [
    /* @__PURE__ */ jsxs("div", { className: "relative flex items-center justify-center", children: [
      /* @__PURE__ */ jsx2(
        "div",
        {
          className: "sat-orb rounded-full",
          style: { width: size, height: size }
        }
      ),
      /* @__PURE__ */ jsx2(
        Satellite,
        {
          className: "absolute text-space-950",
          style: { width: size * 0.5, height: size * 0.5 },
          strokeWidth: 2.2
        }
      )
    ] }),
    withText && /* @__PURE__ */ jsxs("div", { className: "leading-tight", children: [
      /* @__PURE__ */ jsxs("div", { className: "font-extrabold tracking-tight text-white text-lg", children: [
        "Orbit",
        /* @__PURE__ */ jsx2("span", { className: "text-accent", children: "IQ" })
      ] }),
      /* @__PURE__ */ jsx2("div", { className: "text-[10px] uppercase tracking-[0.2em] text-slate-400", children: "Satellite Intelligence" })
    ] })
  ] });
}
var init_Logo = __esm({
  "src/components/Logo.jsx"() {
    "use strict";
    init_define_import_meta_env();
  }
});

// src/components/ui.jsx
import { jsx as jsx3, jsxs as jsxs2 } from "react/jsx-runtime";
function Spinner({ className = "h-5 w-5", label = "" }) {
  return /* @__PURE__ */ jsxs2("span", { className: "inline-flex items-center gap-2", children: [
    /* @__PURE__ */ jsxs2("svg", { className: `animate-spin text-accent ${className}`, viewBox: "0 0 24 24", fill: "none", children: [
      /* @__PURE__ */ jsx3("circle", { cx: "12", cy: "12", r: "10", stroke: "currentColor", strokeWidth: "3", className: "opacity-25" }),
      /* @__PURE__ */ jsx3("path", { d: "M22 12a10 10 0 0 0-10-10", stroke: "currentColor", strokeWidth: "3", strokeLinecap: "round" })
    ] }),
    label && /* @__PURE__ */ jsx3("span", { className: "text-sm text-slate-400", children: label })
  ] });
}
function Button({ children, loading, variant = "primary", className = "", ...props }) {
  const styles = variant === "primary" ? "btn-primary" : variant === "ghost" ? "btn-ghost" : variant === "danger" ? "btn-danger" : "btn border border-space-600 text-slate-300 hover:text-accent hover:border-accent";
  return /* @__PURE__ */ jsxs2("button", { className: `${styles} ${className}`, disabled: loading || props.disabled, ...props, children: [
    loading && /* @__PURE__ */ jsx3(Spinner, { className: "h-4 w-4" }),
    children
  ] });
}
function Alert({ type = "error", title, children }) {
  const styles = {
    error: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    info: "border-accent/40 bg-accent/10 text-accent-soft",
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
  };
  const icons = { error: "\u2715", warn: "!", info: "\u24D8", success: "\u2713" };
  return /* @__PURE__ */ jsxs2("div", { className: `flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${styles[type]}`, children: [
    /* @__PURE__ */ jsx3("span", { className: "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-xs font-bold", children: icons[type] }),
    /* @__PURE__ */ jsxs2("div", { className: "min-w-0", children: [
      title && /* @__PURE__ */ jsx3("div", { className: "mb-0.5 font-semibold", children: title }),
      /* @__PURE__ */ jsx3("div", { children })
    ] })
  ] });
}
var init_ui = __esm({
  "src/components/ui.jsx"() {
    "use strict";
    init_define_import_meta_env();
  }
});

// src/components/AuthLayout.jsx
import { jsx as jsx4, jsxs as jsxs3 } from "react/jsx-runtime";
function AuthLayout({ title, subtitle, children, footer }) {
  return /* @__PURE__ */ jsxs3("div", { className: "relative flex min-h-[100dvh] flex-col overflow-x-hidden", children: [
    /* @__PURE__ */ jsxs3("div", { "aria-hidden": "true", className: "pointer-events-none fixed inset-0 overflow-hidden", children: [
      /* @__PURE__ */ jsx4("div", { className: "absolute -top-40 left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-accent/[0.07] blur-[130px]" }),
      /* @__PURE__ */ jsx4("div", { className: "absolute -bottom-32 -right-24 h-72 w-72 rounded-full bg-accent-deep/[0.08] blur-3xl" })
    ] }),
    /* @__PURE__ */ jsx4("main", { className: "relative flex flex-1 items-center justify-center px-4 py-10 sm:px-6 sm:py-14", children: /* @__PURE__ */ jsxs3("div", { className: "w-full max-w-[26rem] animate-fade-up", children: [
      /* @__PURE__ */ jsx4("div", { className: "mb-6 flex justify-center", children: /* @__PURE__ */ jsx4(Logo, { size: 38 }) }),
      /* @__PURE__ */ jsxs3("div", { className: "card relative overflow-hidden p-6 sm:p-8", children: [
        /* @__PURE__ */ jsx4(
          "div",
          {
            "aria-hidden": "true",
            className: "absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent"
          }
        ),
        /* @__PURE__ */ jsxs3("header", { children: [
          /* @__PURE__ */ jsx4("h1", { className: "text-xl font-bold tracking-tight text-white sm:text-2xl", children: title }),
          subtitle && /* @__PURE__ */ jsx4("p", { className: "mt-1.5 text-sm text-slate-400", children: subtitle })
        ] }),
        /* @__PURE__ */ jsx4("div", { className: "mt-6", children })
      ] }),
      footer && /* @__PURE__ */ jsx4("div", { className: "mt-5 text-center text-sm text-slate-400", children: footer })
    ] }) })
  ] });
}
function SessionBootScreen({ label = "Restoring session\u2026" }) {
  return /* @__PURE__ */ jsxs3("div", { className: "flex min-h-[100dvh] flex-col items-center justify-center gap-6 px-4", children: [
    /* @__PURE__ */ jsx4(Logo, { size: 38, className: "justify-center" }),
    /* @__PURE__ */ jsx4(Spinner, { className: "h-6 w-6", label })
  ] });
}
var init_AuthLayout = __esm({
  "src/components/AuthLayout.jsx"() {
    "use strict";
    init_define_import_meta_env();
    init_Logo();
    init_ui();
  }
});

// src/components/ProtectedRoute.jsx
var ProtectedRoute_exports = {};
__export(ProtectedRoute_exports, {
  GuestRoute: () => GuestRoute,
  default: () => ProtectedRoute
});
import { Navigate, useLocation } from "react-router-dom";
import { jsx as jsx5 } from "react/jsx-runtime";
function ProtectedRoute({ children }) {
  const { user, loading, booting } = useAuth();
  const location2 = useLocation();
  if (booting || loading) return /* @__PURE__ */ jsx5(SessionBootScreen, {});
  if (!user) {
    return /* @__PURE__ */ jsx5(Navigate, { to: "/login", state: { from: location2 }, replace: true });
  }
  return children;
}
function GuestRoute({ children }) {
  const { user, booting } = useAuth();
  if (booting) return /* @__PURE__ */ jsx5(SessionBootScreen, {});
  if (user) return /* @__PURE__ */ jsx5(Navigate, { to: "/dashboard", replace: true });
  return children;
}
var init_ProtectedRoute = __esm({
  "src/components/ProtectedRoute.jsx"() {
    "use strict";
    init_define_import_meta_env();
    init_AuthContext();
    init_AuthLayout();
  }
});

// src/components/auth/OtpVerificationCard.tsx
import { useEffect as useEffect2, useRef, useState } from "react";
import { MailCheck, RotateCw } from "lucide-react";
import { jsx as jsx6, jsxs as jsxs4 } from "react/jsx-runtime";
function OtpVerificationCard({
  email,
  demoCode,
  resendCooldownSeconds = 30,
  onVerify,
  onResend,
  onCancel,
  message
}) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef(null);
  useEffect2(() => {
    if (demoCode) setCode(demoCode);
  }, [demoCode]);
  useEffect2(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);
  const startCooldown = () => {
    setCooldown(resendCooldownSeconds);
    timerRef.current = window.setInterval(() => {
      setCooldown((c) => {
        if (c <= 1 && timerRef.current) window.clearInterval(timerRef.current);
        return Math.max(0, c - 1);
      });
    }, 1e3);
  };
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!/^\d{6}$/.test(code)) return setError("Enter the 6-digit verification code.");
    setLoading(true);
    try {
      await onVerify(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setLoading(false);
    }
  };
  const resend = async () => {
    if (!onResend || cooldown > 0 || loading) return;
    setError("");
    try {
      const next = await onResend();
      if (next) setCode(next);
      startCooldown();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend the code.");
    }
  };
  return /* @__PURE__ */ jsxs4("div", { className: "text-center", children: [
    /* @__PURE__ */ jsx6("span", { className: "mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/40 bg-accent/10 text-accent", children: /* @__PURE__ */ jsx6(MailCheck, { className: "h-6 w-6" }) }),
    /* @__PURE__ */ jsx6("h3", { className: "mt-4 text-lg font-semibold text-white", children: "Verify your email" }),
    /* @__PURE__ */ jsxs4("p", { className: "mx-auto mt-1 max-w-sm text-sm text-slate-400", children: [
      "We sent a 6-digit code to ",
      /* @__PURE__ */ jsx6("span", { className: "font-medium text-slate-200", children: email }),
      ".",
      message ? ` ${message}` : ""
    ] }),
    error && /* @__PURE__ */ jsx6("div", { role: "alert", "aria-live": "polite", className: "mt-4", children: /* @__PURE__ */ jsx6(Alert, { type: "error", children: error }) }),
    /* @__PURE__ */ jsxs4("form", { onSubmit: submit, className: "mt-5", noValidate: true, children: [
      /* @__PURE__ */ jsx6("div", { className: "flex justify-center gap-2", children: Array.from({ length: DIGITS }).map((_, i) => {
        const digit = code[i] ?? "";
        return /* @__PURE__ */ jsx6(
          "input",
          {
            inputMode: "numeric",
            maxLength: 1,
            "aria-label": `Verification code digit ${i + 1} of ${DIGITS}`,
            autoComplete: i === 0 ? "one-time-code" : "off",
            className: "h-12 w-10 rounded-lg border border-space-600 bg-space-850/80 text-center text-lg font-semibold text-white outline-none transition focus:border-accent",
            value: digit,
            onChange: (e) => {
              const v = e.target.value.replace(/\D/g, "");
              const next = code.slice(0, i) + v + code.slice(i + 1);
              setCode(next.slice(0, DIGITS));
              if (v) {
                const el = document.querySelector(
                  `input[maxlength="1"]:nth-of-type(${i + 2})`
                );
                el?.focus();
              }
            },
            onKeyDown: (e) => {
              if (e.key === "Backspace" && !digit) {
                const el = document.querySelector(
                  `input[maxlength="1"]:nth-of-type(${i})`
                );
                el?.focus();
              }
            },
            onPaste: (e) => {
              const text = e.clipboardData.getData("text").replace(/\D/g, "");
              if (text) {
                e.preventDefault();
                setCode(text.slice(0, DIGITS));
              }
            }
          },
          i
        );
      }) }),
      /* @__PURE__ */ jsx6(Button, { type: "submit", loading, className: "mt-5 w-full", children: "Verify & continue" })
    ] }),
    (onResend || onCancel) && /* @__PURE__ */ jsxs4("div", { className: "mt-4 flex items-center justify-center gap-4 text-sm", children: [
      onResend && /* @__PURE__ */ jsxs4(
        "button",
        {
          type: "button",
          disabled: cooldown > 0 || loading,
          onClick: resend,
          className: "inline-flex items-center gap-1.5 font-medium text-accent transition hover:text-accent-soft disabled:cursor-not-allowed disabled:text-slate-500",
          children: [
            /* @__PURE__ */ jsx6(RotateCw, { className: "h-3.5 w-3.5" }),
            cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"
          ]
        }
      ),
      onCancel && /* @__PURE__ */ jsx6("button", { type: "button", onClick: onCancel, className: "font-medium text-slate-400 transition hover:text-slate-200", children: "Use a different email" })
    ] })
  ] });
}
var DIGITS;
var init_OtpVerificationCard = __esm({
  "src/components/auth/OtpVerificationCard.tsx"() {
    "use strict";
    init_define_import_meta_env();
    init_ui();
    DIGITS = 6;
  }
});

// src/components/auth/MfaSetupModal.tsx
import { useEffect as useEffect3, useState as useState2 } from "react";
import { Copy, KeyRound, ShieldCheck, X } from "lucide-react";
import { jsx as jsx7, jsxs as jsxs5 } from "react/jsx-runtime";
function MfaSetupModal({
  open,
  mode = "settings",
  mfaToken,
  onClose,
  onCompleted
}) {
  const completeMfa = useAuthStore((s) => s.completeMfa);
  const [secret, setSecret] = useState2("");
  const [otpauthUrl, setOtpauthUrl] = useState2("");
  const [code, setCode] = useState2("");
  const [error, setError] = useState2("");
  const [loading, setLoading] = useState2(false);
  const [copied, setCopied] = useState2(false);
  const [done, setDone] = useState2(false);
  useEffect3(() => {
    if (!open) return;
    setSecret("");
    setOtpauthUrl("");
    setCode("");
    setError("");
    setDone(false);
    mfaSetup().then((res) => {
      setSecret(res.secret);
      setOtpauthUrl(res.otpauth_url);
    }).catch((err) => setError(err instanceof Error ? err.message : "Could not start MFA setup."));
  }, [open]);
  if (!open) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
    }
  };
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!/^\d{6}$/.test(code)) return setError("Enter a 6-digit authenticator code.");
    setLoading(true);
    try {
      await mfaVerify({ code });
      if (mode === "login" && mfaToken) {
        const user = await completeMfa(mfaToken, code);
        onCompleted?.(user);
      } else {
        setDone(true);
        onCompleted?.(useAuthStore.getState().user);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed. Try again.");
    } finally {
      setLoading(false);
    }
  };
  const closable = mode === "settings";
  return /* @__PURE__ */ jsx7("div", { className: "fixed inset-0 z-[75] flex items-center justify-center bg-space-950/70 px-4 backdrop-blur-sm", children: /* @__PURE__ */ jsxs5("div", { role: "dialog", "aria-modal": "true", "aria-label": "Set up two-factor authentication", className: "card w-full max-w-md p-6", children: [
    /* @__PURE__ */ jsxs5("div", { className: "flex items-start justify-between gap-3", children: [
      /* @__PURE__ */ jsxs5("div", { className: "flex items-center gap-3", children: [
        /* @__PURE__ */ jsx7("span", { className: "flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400", children: /* @__PURE__ */ jsx7(KeyRound, { className: "h-5 w-5" }) }),
        /* @__PURE__ */ jsxs5("div", { children: [
          /* @__PURE__ */ jsx7("h2", { className: "text-lg font-semibold text-white", children: "Two-factor authentication" }),
          /* @__PURE__ */ jsx7("p", { className: "text-xs text-slate-400", children: mode === "login" ? "Required for your organization tier" : "Enrol a TOTP app" })
        ] })
      ] }),
      closable && !loading && /* @__PURE__ */ jsx7(
        "button",
        {
          type: "button",
          onClick: onClose,
          className: "rounded-lg p-1.5 text-slate-400 transition hover:bg-space-800 hover:text-white",
          "aria-label": "Close",
          children: /* @__PURE__ */ jsx7(X, { className: "h-5 w-5" })
        }
      )
    ] }),
    /* @__PURE__ */ jsxs5("div", { className: "mt-5", children: [
      error && /* @__PURE__ */ jsx7("div", { className: "mb-4", children: /* @__PURE__ */ jsx7(Alert, { type: "error", children: error }) }),
      done ? /* @__PURE__ */ jsxs5("div", { className: "text-center", children: [
        /* @__PURE__ */ jsx7("span", { className: "mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400", children: /* @__PURE__ */ jsx7(ShieldCheck, { className: "h-7 w-7" }) }),
        /* @__PURE__ */ jsx7("h3", { className: "mt-4 text-lg font-semibold text-white", children: "Two-factor enabled" }),
        /* @__PURE__ */ jsx7("p", { className: "mt-1 text-sm text-slate-400", children: "Your account now requires an authenticator code to sign in." }),
        closable && /* @__PURE__ */ jsx7(Button, { className: "mt-6 w-full", onClick: onClose, children: "Done" })
      ] }) : /* @__PURE__ */ jsxs5("form", { onSubmit: submit, className: "space-y-4", noValidate: true, children: [
        /* @__PURE__ */ jsxs5("div", { children: [
          /* @__PURE__ */ jsx7("p", { className: "text-sm text-slate-400", children: "Scan the QR code with your authenticator app, or enter the secret manually." }),
          /* @__PURE__ */ jsxs5("div", { className: "mt-3 rounded-xl border border-space-700 bg-space-850/60 p-4", children: [
            /* @__PURE__ */ jsx7("div", { className: "text-xs font-medium uppercase tracking-wider text-slate-500", children: "Setup key (Base32)" }),
            /* @__PURE__ */ jsxs5("div", { className: "mt-1 flex items-center justify-between gap-2", children: [
              /* @__PURE__ */ jsx7("code", { className: "break-all font-mono text-sm text-accent", children: secret || "\u2026" }),
              /* @__PURE__ */ jsx7(
                "button",
                {
                  type: "button",
                  onClick: copy,
                  className: "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-space-600 text-slate-400 transition hover:text-accent",
                  "aria-label": "Copy secret",
                  children: /* @__PURE__ */ jsx7(Copy, { className: "h-4 w-4" })
                }
              )
            ] }),
            otpauthUrl && /* @__PURE__ */ jsx7(
              "a",
              {
                href: otpauthUrl,
                className: "mt-2 inline-block text-xs text-slate-500 underline underline-offset-2 hover:text-accent",
                children: "Open in authenticator"
              }
            ),
            copied && /* @__PURE__ */ jsx7("div", { className: "mt-1 text-xs text-emerald-400", children: "Copied!" })
          ] })
        ] }),
        /* @__PURE__ */ jsxs5("div", { children: [
          /* @__PURE__ */ jsx7("label", { className: "label", children: "6-digit authenticator code" }),
          /* @__PURE__ */ jsx7(
            "input",
            {
              type: "text",
              inputMode: "numeric",
              maxLength: 6,
              className: "input text-center text-lg font-semibold tracking-[0.3em]",
              value: code,
              onChange: (e) => setCode(e.target.value.replace(/\D/g, "")),
              placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022",
              required: true
            }
          )
        ] }),
        /* @__PURE__ */ jsx7(Button, { type: "submit", loading, className: "w-full", children: "Enable two-factor authentication" })
      ] })
    ] })
  ] }) });
}
var init_MfaSetupModal = __esm({
  "src/components/auth/MfaSetupModal.tsx"() {
    "use strict";
    init_define_import_meta_env();
    init_auth();
    init_authStore();
    init_ui();
  }
});

// src/pages/Login.jsx
var Login_exports = {};
__export(Login_exports, {
  default: () => Login
});
import { useState as useState3 } from "react";
import { Link, useLocation as useLocation2, useNavigate } from "react-router-dom";
import { Fragment, jsx as jsx8, jsxs as jsxs6 } from "react/jsx-runtime";
function Login() {
  const navigate = useNavigate();
  const location2 = useLocation2();
  const from = location2.state?.from?.pathname || "/dashboard";
  const login2 = useAuthStore((s) => s.login);
  const completeMfa = useAuthStore((s) => s.completeMfa);
  const resendVerification2 = useAuthStore((s) => s.resendVerification);
  const loading = useAuthStore((s) => s.loading);
  const [email, setEmail] = useState3("");
  const [password, setPassword] = useState3("");
  const [mode, setMode] = useState3("form");
  const [mfaToken, setMfaToken] = useState3("");
  const [mfaCode, setMfaCode] = useState3("");
  const [setupMfaOpen, setSetupMfaOpen] = useState3(false);
  const [error, setError] = useState3("");
  const [fieldErrors, setFieldErrors] = useState3({});
  const [mfaFieldError, setMfaFieldError] = useState3("");
  const [verifyDemo, setVerifyDemo] = useState3(void 0);
  const clearFieldError = (field) => setFieldErrors((prev) => {
    if (!prev[field]) return prev;
    const next = { ...prev };
    delete next[field];
    return next;
  });
  const validateCredentials = () => {
    const problems = {};
    if (!email.trim()) problems.email = "Enter your email address.";
    else if (!EMAIL_RE.test(email.trim())) problems.email = "Enter a valid email address.";
    if (!password) problems.password = "Enter your password.";
    return problems;
  };
  const submit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError("");
    const problems = validateCredentials();
    setFieldErrors(problems);
    if (Object.keys(problems).length) return;
    try {
      await login2({ email: email.trim(), password });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof AuthStepRequired) {
        const res = err.body;
        if (res && res.mfa_setup_required) {
          setError("");
          setSetupMfaOpen(true);
          return;
        }
        if (res && res.mfa_required) {
          setMfaToken(res.mfa_token);
          setMode("mfa");
          return;
        }
      }
      if (err.code === "EMAIL_NOT_VERIFIED") {
        setMode("verify_email");
        setError("");
        return;
      }
      setError(err.message);
    }
  };
  const submitMfa = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError("");
    setMfaFieldError("");
    if (!/^\d{6}$/.test(mfaCode)) return setMfaFieldError("Enter the 6-digit code from your authenticator app.");
    try {
      await completeMfa(mfaToken, mfaCode);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message);
    }
  };
  const handleVerify = async (code) => {
    await verifyEmailFromVerification(code);
  };
  const verifyEmailFromVerification = async (code) => {
    const state = useAuthStore.getState();
    await state.verifyEmail(email, code);
    navigate(from, { replace: true });
  };
  const handleResend = async () => {
    try {
      const next = await resendVerification2(email);
      if (next) setVerifyDemo(next);
      return next;
    } catch (err) {
      setError(err.message);
    }
  };
  return /* @__PURE__ */ jsxs6(
    AuthLayout,
    {
      title: mode === "form" ? "Welcome back" : mode === "verify_email" ? "Verify your email" : "Two-factor authentication",
      subtitle: mode === "form" ? "Access your OrbitIQ workspace." : mode === "verify_email" ? "Enter the 6-digit code we sent to your inbox." : "Enter the code from your authenticator app.",
      children: [
        error && /* @__PURE__ */ jsx8("div", { id: "login-error", role: "alert", "aria-live": "polite", className: "mb-4", children: /* @__PURE__ */ jsx8(Alert, { type: "error", children: error }) }),
        mode === "form" && /* @__PURE__ */ jsxs6(Fragment, { children: [
          /* @__PURE__ */ jsxs6("form", { onSubmit: submit, noValidate: true, "aria-busy": loading, className: "space-y-4", children: [
            /* @__PURE__ */ jsxs6("div", { children: [
              /* @__PURE__ */ jsx8("label", { className: "label", htmlFor: "login-email", children: "Email" }),
              /* @__PURE__ */ jsx8(
                "input",
                {
                  id: "login-email",
                  name: "email",
                  type: "email",
                  inputMode: "email",
                  autoComplete: "email",
                  autoFocus: true,
                  className: "input",
                  placeholder: "you@example.com",
                  value: email,
                  onChange: (e) => {
                    setEmail(e.target.value);
                    clearFieldError("email");
                  },
                  "aria-invalid": fieldErrors.email ? true : void 0,
                  "aria-describedby": fieldErrors.email ? "login-email-error" : void 0,
                  disabled: loading,
                  required: true
                }
              ),
              fieldErrors.email && /* @__PURE__ */ jsx8("p", { id: "login-email-error", className: "mt-1.5 text-xs text-rose-400", children: fieldErrors.email })
            ] }),
            /* @__PURE__ */ jsxs6("div", { children: [
              /* @__PURE__ */ jsxs6("div", { className: "mb-1.5 flex items-center justify-between gap-3", children: [
                /* @__PURE__ */ jsx8("label", { className: "label !mb-0", htmlFor: "login-password", children: "Password" }),
                /* @__PURE__ */ jsx8(Link, { to: "/forgot-password", className: "text-xs font-medium text-accent hover:text-accent-soft", children: "Forgot password?" })
              ] }),
              /* @__PURE__ */ jsx8(
                "input",
                {
                  id: "login-password",
                  name: "password",
                  type: "password",
                  autoComplete: "current-password",
                  className: "input",
                  placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
                  value: password,
                  onChange: (e) => {
                    setPassword(e.target.value);
                    clearFieldError("password");
                  },
                  "aria-invalid": fieldErrors.password ? true : void 0,
                  "aria-describedby": fieldErrors.password ? "login-password-error" : void 0,
                  disabled: loading,
                  required: true
                }
              ),
              fieldErrors.password && /* @__PURE__ */ jsx8("p", { id: "login-password-error", className: "mt-1.5 text-xs text-rose-400", children: fieldErrors.password })
            ] }),
            /* @__PURE__ */ jsx8(Button, { type: "submit", loading, disabled: loading, className: "w-full", children: "Sign in" })
          ] }),
          /* @__PURE__ */ jsxs6("section", { "aria-labelledby": "create-account-heading", className: "mt-6 border-t border-space-700/60 pt-5 text-center", children: [
            /* @__PURE__ */ jsx8(
              "h2",
              {
                id: "create-account-heading",
                className: "text-xs font-semibold uppercase tracking-[0.16em] text-slate-500",
                children: "New to OrbitIQ?"
              }
            ),
            /* @__PURE__ */ jsx8(Link, { to: "/register", className: "btn-ghost mt-3 w-full", children: "Create account" })
          ] })
        ] }),
        mode === "verify_email" && /* @__PURE__ */ jsx8(
          OtpVerificationCard,
          {
            email,
            demoCode: verifyDemo,
            onVerify: handleVerify,
            onResend: handleResend,
            onCancel: () => setMode("form")
          }
        ),
        mode === "mfa" && /* @__PURE__ */ jsxs6(Fragment, { children: [
          /* @__PURE__ */ jsxs6("form", { onSubmit: submitMfa, noValidate: true, "aria-busy": loading, className: "space-y-4", children: [
            /* @__PURE__ */ jsxs6("div", { children: [
              /* @__PURE__ */ jsx8("label", { className: "label", htmlFor: "login-mfa", children: "Authenticator code" }),
              /* @__PURE__ */ jsx8(
                "input",
                {
                  id: "login-mfa",
                  name: "one-time-code",
                  type: "text",
                  inputMode: "numeric",
                  pattern: "[0-9]*",
                  maxLength: 6,
                  autoComplete: "one-time-code",
                  autoFocus: true,
                  className: "input text-center text-lg font-semibold tracking-[0.3em]",
                  value: mfaCode,
                  onChange: (e) => {
                    setMfaCode(e.target.value.replace(/\D/g, ""));
                    setMfaFieldError("");
                  },
                  "aria-invalid": mfaFieldError ? true : void 0,
                  "aria-describedby": mfaFieldError ? "login-mfa-error" : void 0,
                  placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022",
                  disabled: loading,
                  required: true
                }
              ),
              mfaFieldError && /* @__PURE__ */ jsx8("p", { id: "login-mfa-error", className: "mt-1.5 text-xs text-rose-400", children: mfaFieldError })
            ] }),
            /* @__PURE__ */ jsx8(Button, { type: "submit", loading, disabled: loading, className: "w-full", children: "Verify & sign in" })
          ] }),
          /* @__PURE__ */ jsx8("div", { className: "mt-6 border-t border-space-700/60 pt-4 text-center", children: /* @__PURE__ */ jsx8(
            "button",
            {
              type: "button",
              onClick: () => {
                setMfaFieldError("");
                setError("");
                setMode("form");
              },
              className: "text-xs font-medium text-slate-400 transition hover:text-accent",
              children: "Back to sign in"
            }
          ) })
        ] }),
        /* @__PURE__ */ jsx8(
          MfaSetupModal,
          {
            open: setupMfaOpen,
            mode: "login",
            mfaToken: useAuthStore.getState().mfaStep?.mfaToken,
            onCompleted: () => navigate(from, { replace: true })
          }
        )
      ]
    }
  );
}
var EMAIL_RE;
var init_Login = __esm({
  "src/pages/Login.jsx"() {
    "use strict";
    init_define_import_meta_env();
    init_auth();
    init_AuthLayout();
    init_OtpVerificationCard();
    init_MfaSetupModal();
    init_authStore();
    init_ui();
    EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  }
});

// .smoke/harness.mjs
init_define_import_meta_env();

// .smoke/shim.mjs
init_define_import_meta_env();
var bag = /* @__PURE__ */ new Map();
globalThis.localStorage = {
  getItem: (k) => bag.has(k) ? bag.get(k) : null,
  setItem: (k, v) => void bag.set(k, String(v)),
  removeItem: (k) => void bag.delete(k),
  clear: () => bag.clear(),
  get length() {
    return bag.size;
  },
  key: (i) => Array.from(bag.keys())[i] ?? null
};
globalThis.fetch = async () => ({ status: 200, ok: true, json: async () => ({}) });

// .smoke/harness.mjs
init_zustand_shim();
var calls = [];
var responder = () => ({ status: 200, ok: true, body: {} });
globalThis.fetch = async (url, opts = {}) => {
  calls.push({ url, method: opts.method || "GET", body: opts.body });
  const res = responder(url, opts);
  return { status: res.status, ok: res.ok, json: async () => res.body };
};
var fs = await import("node:fs");
var React = (await import("react")).default;
var { renderToStaticMarkup } = await import("react-dom/server");
var { MemoryRouter, Routes, Route } = await import("react-router-dom");
var { default: ProtectedRoute2, GuestRoute: GuestRoute2 } = await Promise.resolve().then(() => (init_ProtectedRoute(), ProtectedRoute_exports));
var { AuthProvider: AuthProvider2 } = await Promise.resolve().then(() => (init_AuthContext(), AuthContext_exports));
var { default: Login2 } = await Promise.resolve().then(() => (init_Login(), Login_exports));
var { useAuthStore: useAuthStore2 } = await Promise.resolve().then(() => (init_authStore(), authStore_exports));
var { getTokens: getTokens2, setTokens: setTokens2, setSessionId: setSessionId2 } = await Promise.resolve().then(() => (init_client(), client_exports));
var pass = 0;
var failures = [];
var check = (name, ok, extra = "") => {
  if (ok) {
    pass += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures.push(name);
    console.log(`FAIL  ${name} ${extra}`);
  }
};
function withState(patch, render) {
  setStateOverride(() => patch);
  try {
    return render();
  } finally {
    setStateOverride(null);
  }
}
function renderEntry(path, state) {
  return withState(
    state,
    () => renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        { initialEntries: [path] },
        React.createElement(
          AuthProvider2,
          null,
          React.createElement(
            Routes,
            null,
            React.createElement(Route, {
              path: "/",
              element: React.createElement(GuestRoute2, null, React.createElement(Login2, null))
            }),
            React.createElement(Route, {
              path: "/dashboard",
              element: React.createElement(
                ProtectedRoute2,
                null,
                React.createElement("div", null, "APP_WORKSPACE_MARKER")
              )
            })
          )
        )
      )
    )
  );
}
var html = renderEntry("/", { user: null, booting: false, loading: false });
var bodyIndex = (s) => html.indexOf(s);
check("renders the login screen", html.includes("Welcome back") && html.includes("Access your OrbitIQ workspace"));
check("no marketing / landing copy", ["Ask the Earth", "Built for real questions", "Try demo", "demo datasets", "Demo accounts"].every((s) => !html.includes(s)));
check("no hardcoded credentials", !html.includes("Admin@123") && !/demo@|admin@/.test(html));
check(
  "email field is label-associated",
  html.includes('for="login-email"') && html.includes('id="login-email"')
);
check(
  "password field is label-associated",
  html.includes('for="login-password"') && html.includes('id="login-password"')
);
check(
  "fields carry name + autocomplete hints",
  /id="login-email"[^>]*name="email"/.test(html) && /autocomplete="email"/i.test(html) && /id="login-password"[^>]*name="password"/.test(html) && /autocomplete="current-password"/i.test(html)
);
check("password input is masked", html.includes('type="password"') && !html.includes('type="text" id="login-password"'));
check(
  "single form wraps the credentials + submit button",
  (html.match(/<form/g) || []).length === 1 && html.indexOf("<form") < bodyIndex("Forgot password?") && html.indexOf("</form>") > bodyIndex("Sign in")
);
check(
  "form opts out of native bubbles and tracks busy state",
  html.includes("novalidate") && html.includes('aria-busy="false"')
);
check(
  "forgot-password link sits in the password row",
  bodyIndex("Password") < bodyIndex("Forgot password?") && html.includes('href="/forgot-password"')
);
var sectionIdx = bodyIndex("create-account-heading");
check(
  "create-account section is a labelled region inside the card",
  sectionIdx > bodyIndex("</form>") && html.includes('aria-labelledby="create-account-heading"') && html.includes('id="create-account-heading"') && sectionIdx < bodyIndex("</main>")
);
check(
  "create-account section has a heading + full-width secondary action",
  html.includes("New to OrbitIQ?") && html.includes('href="/register"') && /class="btn-ghost mt-3 w-full"[^>]*>Create account</.test(html.replace(/<a /g, "<a "))
);
check(
  "create account appears exactly once (no duplicated footer link)",
  (html.match(/Create account/g) || []).length === 1
);
var anonDashboard = renderEntry("/dashboard", { user: null, booting: false, loading: false });
check("anonymous visitor is blocked from protected routes", !anonDashboard.includes("APP_WORKSPACE_MARKER"));
var authedUser = { id: "u1", name: "Ava Analyst", email: "ava@orbitiq.ai", role: "analyst" };
var authedEntry = renderEntry("/", { user: authedUser, booting: false, loading: false });
check(
  "authenticated visitor never sees the login form",
  authedEntry.length === 0 && !authedEntry.includes("Welcome back")
);
var authedDashboard = renderEntry("/dashboard", { user: authedUser, booting: false, loading: false });
check("authenticated visitor reaches the protected app", authedDashboard.includes("APP_WORKSPACE_MARKER"));
var bootHtml = renderEntry("/", { user: null, booting: true, loading: false });
check("session restore shows the boot splash", bootHtml.includes("Restoring session") && !bootHtml.includes("Welcome back"));
var appSource = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
check(
  "'/' is wired to Login inside GuestRoute, with no marketing route",
  /path="\/"\s+element=\{<GuestRoute><Login \/><\/GuestRoute>\}/.test(appSource) && !/Landing/.test(appSource)
);
check(
  "app deep links are preserved",
  ["/dashboard", "/results", "/results/:resultId", "/history", "/datasets", "/weather", "/predictions", "/geotools", "/saved", "/settings", "/howto", "/404"].every((p) => appSource.includes(`path="${p}"`))
);
var tokens = (n) => ({ access_token: `acc-${n}`, refresh_token: `ref-${n}`, session_id: `sid-${n}` });
calls = [];
responder = () => ({ status: 200, ok: true, body: { user: authedUser, ...tokens(1) } });
var loggedIn = await useAuthStore2.getState().login({ email: "ava@orbitiq.ai", password: "Password1" });
check(
  "valid login calls POST /api/v1/auth/login with the payload",
  calls[0]?.url === "/api/v1/auth/login" && calls[0].method === "POST" && JSON.parse(calls[0].body).email === "ava@orbitiq.ai"
);
check(
  "valid login stores + persists the session",
  getTokens2().accessToken === "acc-1" && bag.get("satquery_access") === "acc-1" && loggedIn.email === authedUser.email
);
setTokens2(null, null);
setSessionId2(null);
bag.clear();
responder = () => ({ status: 401, ok: false, body: { detail: "Invalid email or password.", code: "HTTP_ERROR" } });
var invalidErr = null;
try {
  await useAuthStore2.getState().login({ email: "ava@orbitiq.ai", password: "wrong" });
} catch (e) {
  invalidErr = e;
}
check(
  "invalid login surfaces the backend message",
  invalidErr?.message === "Invalid email or password." && !bag.has("satquery_access"),
  invalidErr ? invalidErr.message : "no error"
);
responder = () => ({ status: 403, ok: false, body: { detail: "verify your email", code: "EMAIL_NOT_VERIFIED" } });
var otpErr = null;
try {
  await useAuthStore2.getState().login({ email: "new@orbitiq.ai", password: "Password1" });
} catch (e) {
  otpErr = e;
}
check("unverified login raises EMAIL_NOT_VERIFIED (OTP flow)", otpErr?.code === "EMAIL_NOT_VERIFIED");
calls = [];
responder = () => ({ status: 200, ok: true, body: { user: { ...authedUser, email: "new@orbitiq.ai" }, ...tokens("otp") } });
var otpUser = await useAuthStore2.getState().verifyEmail("new@orbitiq.ai", "123456");
check(
  "OTP verification signs the account in",
  calls[0].url === "/api/v1/auth/verify-email" && otpUser.email === "new@orbitiq.ai" && getTokens2().accessToken === "acc-otp"
);
calls = [];
responder = () => ({ status: 401, ok: false, body: { detail: "Invalid authenticator code.", code: "MFA_INVALID" } });
var mfaErr = null;
try {
  await useAuthStore2.getState().completeMfa("tok", "000000");
} catch (e) {
  mfaErr = e;
}
check(
  "MFA challenge endpoint + error code preserved",
  calls[0].url === "/api/v1/auth/mfa/challenge" && mfaErr?.code === "MFA_INVALID"
);
setTokens2("expired", null);
setSessionId2("sid");
responder = () => ({ status: 401, ok: false, body: { detail: "Account unavailable." } });
var sessionErr = null;
try {
  await useAuthStore2.getState().refreshUser();
} catch (e) {
  sessionErr = e;
}
check(
  "authenticated 401 still reports an expired session and clears tokens",
  sessionErr?.message === "Your session expired. Please sign in again." && getTokens2().accessToken === ""
);
console.log(`
${pass} passed, ${failures.length} failed`);
if (failures.length) {
  console.log("failed:", failures.join(" | "));
  process.exit(1);
}
