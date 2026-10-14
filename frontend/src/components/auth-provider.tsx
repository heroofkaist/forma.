"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { API_URL, authenticatedFetch } from "../lib/api";

type AuthIdentity = { role: string; username: string | null; student_id: string | null; account_id?: string | null };
type AuthContextValue = {
  enabled: boolean;
  loading: boolean;
  user: AuthIdentity | null;
  login: (role: string, username: string, password: string) => Promise<void>;
  logout: () => void;
};

function publicPath(pathname: string) {
  return ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email"].includes(pathname);
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<AuthIdentity | null>(null);
  const pathname = usePathname();
  const router = useRouter();

  const loadIdentity = useCallback(async () => {
    const response = await authenticatedFetch(`${API_URL}/api/auth/me`);
    if (!response.ok) throw new Error("Authentication required.");
    return await response.json() as AuthIdentity;
  }, []);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/auth/status`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Unable to read authentication status.");
        return await response.json() as { required: boolean };
      })
      .then(async ({ required }) => {
        if (!active) return;
        setEnabled(required);
        if (required) {
          try {
            const identity = await loadIdentity();
            if (active) setUser(identity);
          } catch {
            window.sessionStorage.removeItem("forma_access_token");
          }
        }
      })
      .catch(() => {
        if (active) setEnabled(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [loadIdentity]);

  useEffect(() => {
    if (loading || !enabled || publicPath(pathname)) return;
    if (!user) {
      const next = pathname || "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    const isStudentPath = pathname.startsWith("/student");
    if (user.role === "student" && !isStudentPath) router.replace("/student");
    if (user.role === "teacher" && isStudentPath) router.replace("/");
  }, [enabled, loading, pathname, router, user]);

  const login = useCallback(async (role: string, username: string, password: string) => {
    const response = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, username, password }),
    });
    const body = await response.json().catch(() => null) as { access_token?: string; detail?: string } | null;
    if (!response.ok) {
      throw new Error(body?.detail ?? "Не удалось войти.");
    }
    window.sessionStorage.removeItem("forma_access_token");
    try {
      setUser(await loadIdentity());
    } catch (error) {
      window.sessionStorage.removeItem("forma_access_token");
      throw error;
    }
  }, [loadIdentity]);

  const logout = useCallback(() => {
    void authenticatedFetch(`${API_URL}/api/auth/logout`, { method: "POST" }).then((response) => {
      if (!response.ok) throw new Error("Unable to sign out. Please try again.");
      window.sessionStorage.removeItem("forma_access_token");
      setUser(null);
      router.replace("/login");
    }).catch((error: unknown) => window.alert(error instanceof Error ? error.message : "Unable to sign out."));
  }, [router]);

  const value = useMemo(() => ({ enabled, loading, user, login, logout }), [
    enabled, loading, user, login, logout,
  ]);
  const isLogin = publicPath(pathname);
  const wrongRolePath = enabled && user && (
    (user.role === "student" && !pathname.startsWith("/student") && !isLogin)
    || (user.role === "teacher" && pathname.startsWith("/student"))
  );
  return (
    <AuthContext.Provider value={value}>
      {loading && !isLogin ? <div className="auth-loading" aria-live="polite">Forma загружается…</div> : null}
      {!loading && enabled && !user && !isLogin
        ? <div className="auth-loading" aria-live="polite">Требуется вход…</div>
        : wrongRolePath
          ? <div className="auth-loading" aria-live="polite">Переходим в вашу рабочую область…</div>
          : children}
    </AuthContext.Provider>
  );
}
