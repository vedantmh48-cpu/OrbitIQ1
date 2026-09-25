import { createContext, useContext, useEffect, useMemo } from "react";
import { useAuthStore } from "../store/authStore";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const user = useAuthStore(s => s.user);
  const loading = useAuthStore(s => s.loading);
  const booting = useAuthStore(s => s.booting);
  const login = useAuthStore(s => s.login);
  const register = useAuthStore(s => s.register);
  const logout = useAuthStore(s => s.logout);
  const refreshUser = useAuthStore(s => s.refreshUser);
  const hydrate = useAuthStore(s => s.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const value = useMemo(
    () => ({ user, login, register, logout, refreshUser, loading, booting }),
    [user, login, register, logout, refreshUser, loading, booting]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}