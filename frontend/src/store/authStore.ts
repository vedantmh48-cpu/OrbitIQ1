/**
 * Zustand auth store - the single source of truth for session state.
 * Existing Context consumers (AuthContext) are an adapter over this store.
 */
import { create } from "zustand";
import { getSessionId, getTokens, setSessionId, setTokens } from "../api/client";
import * as authApi from "../api/auth";
import type {
  IdleConfig,
  LoginRequest,
  LoginResponse,
  RegistrationPayload,
  SessionRevokedReason,
  User,
} from "../types/auth";

const USER_KEY = "satquery_user";

const ALL_OPTIONS: number[] = [5, 15, 30, 60];

function isGovOrg(user: User | null): boolean {
  return (
    !!user &&
    user.account_type === "organization" &&
    (user.org_type === "government" || user.org_type === "defense")
  );
}

function loadStoredUser(): User | null {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

function persistUser(user: User | null) {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  else localStorage.removeItem(USER_KEY);
}

export function computeIdleConfig(user: User | null): IdleConfig {
  const gov = isGovOrg(user);
  const selectable = gov ? ALL_OPTIONS.filter((o) => o <= 15) : [...ALL_OPTIONS];
  return {
    timeoutMinutes: user?.inactivity_timeout_minutes ?? 15,
    warningLeadSeconds: 60,
    maxTimeoutMinutes: gov ? 15 : 60,
    governmentTier: gov,
    selectableOptions: selectable,
  };
}

interface AuthState {
  user: User | null;
  loading: boolean;
  booting: boolean;
  /** Pending post-registration email verification. */
  pendingVerification: { email: string } | null;
  /** Half-opened login awaiting a TOTP challenge. */
  mfaStep: { mfaToken: string; email: string; setupRequired: boolean } | null;

  hydrate: () => Promise<void>;
  register: (payload: RegistrationPayload) => Promise<{ user: User; demoCode?: string }>;
  resendVerification: (email: string) => Promise<string | undefined>;
  verifyEmail: (email: string, code: string) => Promise<User>;
  login: (params: LoginRequest) => Promise<User>;
  completeMfa: (mfaToken: string, code: string) => Promise<User>;
  logout: (reason?: SessionRevokedReason) => Promise<void>;
  heartbeat: () => Promise<boolean>;
  refreshUser: () => Promise<User>;
  setMfaStep: (step: AuthState["mfaStep"]) => void;
  clearPendingVerification: () => void;
}

function applySession(user: User, tokens: { access_token: string; refresh_token: string; session_id: string }) {
  setTokens(tokens.access_token, tokens.refresh_token);
  setSessionId(tokens.session_id);
  persistUser(user);
}

export const useAuthStore = create<AuthState>((set) => ({
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
      const me = await authApi.apiGetMe();
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
      const res = await authApi.register(payload);
      set({ pendingVerification: { email: res.email } });
      return { user: res.user, demoCode: res.demo_code };
    } finally {
      set({ loading: false });
    }
  },

  resendVerification: async (email) => {
    const res = await authApi.resendVerification(email);
    return res.demo_code;
  },

  verifyEmail: async (email, code) => {
    set({ loading: true });
    try {
      const res = await authApi.verifyEmail(email, code);
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
      const res: LoginResponse = await authApi.login(params);
      if ("mfa_required" in res && res.mfa_required) {
        set({ mfaStep: { mfaToken: res.mfa_token, email: res.email, setupRequired: false } });
        throw new authApi.AuthStepRequired(res);
      }
      if ("mfa_setup_required" in res && res.mfa_setup_required) {
        set({
          mfaStep: { mfaToken: res.mfa_token, email: res.email, setupRequired: true },
          user: res.user,
        });
        throw new authApi.AuthStepRequired(res);
      }
      // Success branch: full tokens + user payload.
      if (!("mfa_required" in res) && !("mfa_setup_required" in res)) {
        applySession(res.user, {
          access_token: res.access_token,
          refresh_token: res.refresh_token,
          session_id: res.session_id,
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
      const res = await authApi.mfaChallenge({ mfa_token: mfaToken, code });
      applySession(res.user, res);
      set({ user: res.user, mfaStep: null, loading: false });
      return res.user;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  logout: async (reason?: SessionRevokedReason) => {
    const { refreshToken } = getTokens();
    try {
      if (refreshToken) await authApi.logout(refreshToken);
    } catch {
      /* best effort - clear locally regardless */
    }
    setTokens(null, null);
    setSessionId(null);
    persistUser(null);
    set({ user: null, mfaStep: null, loading: false, pendingVerification: null });
    const from = reason ? `?reason=${encodeURIComponent(reason)}` : "";
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = `/login${from}`;
    }
  },

  heartbeat: async () => {
    try {
      await authApi.heartbeat();
      return true;
    } catch {
      return false;
    }
  },

  refreshUser: async () => {
    const me = await authApi.apiGetMe();
    persistUser(me);
    set({ user: me });
    return me;
  },

  setMfaStep: (step) => set({ mfaStep: step }),
  clearPendingVerification: () => set({ pendingVerification: null }),
}));

/** Non-reactive accessor (used by the idle timer / WS listeners). */
export function getAuthSnapshot() {
  return useAuthStore.getState();
}