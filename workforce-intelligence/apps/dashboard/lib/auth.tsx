"use client";

// Client-side auth context: holds the JWT + current user, persists the token
// in localStorage, and redirects to /login on logout or any 401 from the API.
// For SUPER_ADMIN it also tracks the active organization that org-scoped pages
// act on (other roles are pinned to their own organization by the API).

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
  forgetActiveOrganization,
  getStoredActiveOrganization,
  getToken,
  setActiveOrganization,
  setToken,
  UNAUTHORIZED_EVENT,
} from "./api";
import type { LoginRequest, Me, OrganizationSummary, Role } from "./types";

/** ORG_ADMIN and SUPER_ADMIN can see admin / provisioning surfaces. */
export function isAdminRole(role: Role | null | undefined): boolean {
  return role === "ORG_ADMIN" || role === "SUPER_ADMIN";
}

interface AuthState {
  /** false until the token has been read from localStorage on the client. */
  ready: boolean;
  token: string | null;
  me: Me | null;
  /** SUPER_ADMIN only: every organization (null until loaded / other roles). */
  organizations: OrganizationSummary[] | null;
  /** The organization org-scoped pages act on (own org for non-super roles). */
  activeOrgId: string | null;
  /** true once activeOrgId is settled for the signed-in user. */
  orgReady: boolean;
  /** SUPER_ADMIN: switch the active organization. */
  selectOrg: (id: string | null) => void;
  /** SUPER_ADMIN: reload the organization list (e.g. after creating one). */
  refreshOrganizations: () => Promise<OrganizationSummary[]>;
  login: (creds: LoginRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [token, setTokenState] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationSummary[] | null>(null);
  const [superOrgId, setSuperOrgId] = useState<string | null>(null);
  const [orgsLoaded, setOrgsLoaded] = useState(false);

  const isSuper = me?.role === "SUPER_ADMIN";

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

  // Set the API-layer org before re-rendering, so pages that mount on the new
  // org never fire a request without it.
  const selectOrg = useCallback((id: string | null) => {
    setActiveOrganization(id);
    setSuperOrgId(id);
  }, []);

  const refreshOrganizations = useCallback(async () => {
    const list = await api.organizations();
    setOrganizations(list);
    return list;
  }, []);

  // Super admins: load the tenants and restore (or auto-pick) the active one.
  useEffect(() => {
    if (!isSuper) {
      forgetActiveOrganization();
      setOrganizations(null);
      setSuperOrgId(null);
      setOrgsLoaded(false);
      return;
    }
    let cancelled = false;
    api
      .organizations()
      .then((list) => {
        if (cancelled) return;
        setOrganizations(list);
        const stored = getStoredActiveOrganization();
        const pick =
          list.find((o) => o.id === stored)?.id ?? (list.length === 1 ? list[0].id : null);
        selectOrg(pick);
      })
      .catch(() => {
        if (!cancelled) setOrganizations([]);
      })
      .finally(() => {
        if (!cancelled) setOrgsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [isSuper, selectOrg]);

  const logout = useCallback(() => {
    clearToken();
    forgetActiveOrganization();
    setTokenState(null);
    setMe(null);
    router.replace("/login");
  }, [router]);

  // Global 401 handler: the API layer dispatches UNAUTHORIZED_EVENT.
  useEffect(() => {
    const handler = () => {
      forgetActiveOrganization();
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

  const activeOrgId = isSuper ? superOrgId : me?.organization_id ?? null;
  const orgReady = me ? (isSuper ? orgsLoaded : true) : false;

  const value = useMemo<AuthState>(
    () => ({
      ready,
      token,
      me,
      organizations,
      activeOrgId,
      orgReady,
      selectOrg,
      refreshOrganizations,
      login,
      logout,
    }),
    [
      ready,
      token,
      me,
      organizations,
      activeOrgId,
      orgReady,
      selectOrg,
      refreshOrganizations,
      login,
      logout,
    ]
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
