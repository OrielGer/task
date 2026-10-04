"use client";

import type { ReactNode } from "react";

import { useRequireAuth } from "@/lib/auth";
import { Loading } from "@/components/ui";

/**
 * Wraps a protected page. While auth is hydrating it shows a loading state;
 * if there is no token it renders nothing (the guard redirects to /login).
 */
export function Protected({ children }: { children: ReactNode }) {
  const { ready, token } = useRequireAuth();

  if (!ready) return <Loading label="Checking session…" />;
  if (!token) return <Loading label="Redirecting to sign in…" />;
  return <>{children}</>;
}
