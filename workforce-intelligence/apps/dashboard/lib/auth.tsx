"use client";

// Client-side auth context: holds the JWT + current user, persists the token
// in localStorage, and redirects to /login on logout or any 401 from the API.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  api,
  clearToken,
  getToken,
  setToken,
  UNAUTHORIZED_EVENT,
} from "./api";
import type { LoginRequest, Me } from "./types";

interface AuthState {
  /** false until the token has been read from localStorage on the client. */
  ready: boolean;
  token: string | null;
  me: Me | null;
  login: (creds: LoginRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [token, setTokenState] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  // Hydrate token from storage once, on mount.
  useEffect(() => {
    const existing = getToken();
    setTokenState(existing);
    setReady(true);
  }, []);

  // When we have a token but no profile, load it.
  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    const controller = new AbortController();
    api
      .me(controller.signal)
      .then((profile) => setMe(profile))
      .catch(() => {
        /* 401 handled globally; other errors leave me null */
      });
    return () => controller.abort();
  }, [token]);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setMe(null);
    router.replace("/login");
  }, [router]);

  // Global 401 handler: the API layer dispatches UNAUTHORIZED_EVENT.
  useEffect(() => {
    const handler = () => {
      setTokenState(null);
      setMe(null);
      router.replace("/login");
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [router]);

  const login = useCallback(async (creds: LoginRequest) => {
    const res = await api.login(creds);
    setToken(res.access_token);
    setTokenState(res.access_token);
    try {
      const profile = await api.me();
      setMe(profile);
    } catch {
      /* non-fatal; profile will be retried by the effect */
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ ready, token, me, login, logout }),
    [ready, token, me, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/**
 * Guard hook for protected pages: redirects to /login once we know there is no
 * token. Returns the current auth state so the page can show a loading state
 * while `ready` is false.
 */
export function useRequireAuth(): AuthState {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const redirected = useRef(false);

  useEffect(() => {
    if (auth.ready && !auth.token && !redirected.current) {
      redirected.current = true;
      router.replace("/login");
    }
  }, [auth.ready, auth.token, router, pathname]);

  return auth;
}
