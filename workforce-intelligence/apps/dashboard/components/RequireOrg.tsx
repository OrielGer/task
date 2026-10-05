"use client";

import { Fragment, type ReactNode } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/auth";
import { Loading } from "@/components/ui";

/**
 * Wraps org-scoped page content. A super admin has no organization of their own,
 * so they must pick one (top bar) first. The subtree is keyed by the active org,
 * so switching organizations remounts the page and reloads its data.
 */
export function RequireOrg({ children }: { children: ReactNode }) {
  const { me, orgReady, activeOrgId, organizations } = useAuth();

  if (!me || !orgReady) return <Loading label="Loading organization…" />;

  if (me.role === "SUPER_ADMIN" && !activeOrgId) {
    return (
      <div className="notice">
        {organizations && organizations.length > 0 ? (
          "Choose an organization in the top bar to see its data."
        ) : (
          <>
            No organizations yet. <Link href="/admin">Create one in Admin</Link> to get started.
          </>
        )}
      </div>
    );
  }

  return <Fragment key={activeOrgId ?? "own"}>{children}</Fragment>;
}
