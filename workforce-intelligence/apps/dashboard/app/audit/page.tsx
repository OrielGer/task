"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { isAdminRole, useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { ErrorNotice, Loading } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { AuditPage as AuditPageData } from "@/lib/types";

const PAGE_SIZE = 25;

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function AuditInner() {
  const { me } = useAuth();
  const isSuper = me?.role === "SUPER_ADMIN";
  const [superOrgId, setSuperOrgId] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AuditPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // SUPER_ADMIN passes organization_id; org-scoped roles omit it.
  const readOrgParam = isSuper ? superOrgId.trim() || undefined : undefined;

  const load = useCallback(
    (signal?: AbortSignal) => {
      setError(null);
      api
        .audit({ organizationId: readOrgParam, limit: PAGE_SIZE, offset }, signal)
        .then(setData)
        .catch((err) => {
          if (isAbort(err)) return;
          if (err instanceof ApiError && err.status === 401) return;
          setError(err instanceof Error ? err.message : "Failed to load audit log.");
        });
    },
    [readOrgParam, offset]
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (!me) return <Loading label="Loading your profile…" />;

  if (!isAdminRole(me.role)) {
    return (
      <>
        <h1 className="page-title">Audit log</h1>
        <ErrorNotice message="You are not authorized to view this page." />
      </>
    );
  }

  const total = data?.total ?? 0;
  const shown = data?.items.length ?? 0;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = offset + shown;
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <>
      <h1 className="page-title">Audit log</h1>
      <p className="page-sub">
        A record of who viewed which employee data, and when.
      </p>

      {isSuper ? (
        <div className="card">
          <h2>Active organization</h2>
          <p className="muted small" style={{ marginTop: -6, marginBottom: 14 }}>
            Super admins must choose the organization whose audit log to read.
          </p>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="audit-org">Organization id</label>
            <input
              id="audit-org"
              value={superOrgId}
              onChange={(e) => {
                setOffset(0);
                setSuperOrgId(e.target.value);
              }}
              placeholder="organization id"
            />
          </div>
        </div>
      ) : null}

      {error ? <ErrorNotice message={error} /> : null}

      <div className="card">
        <div className="card-head">
          <h2>Access events</h2>
          <span className="small muted">
            {total > 0 ? `${rangeStart}–${rangeEnd} of ${total}` : "0 events"}
          </span>
        </div>

        {!data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <div className="notice">No audit events for this selection.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Resource type</th>
                  <th>Resource id</th>
                  <th>Employee id</th>
                  <th>Viewer user id</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id}>
                    <td className="muted small">{formatDateTime(e.created_at)}</td>
                    <td>
                      <strong>{e.action}</strong>
                    </td>
                    <td className="muted">{e.resource_type}</td>
                    <td className="mono small">{e.resource_id ?? "—"}</td>
                    <td className="mono small">{e.employee_id ?? "—"}</td>
                    <td className="mono small">{e.viewer_user_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="row" style={{ marginTop: 16, justifyContent: "space-between" }}>
          <button
            className="small-btn"
            disabled={!hasPrev}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          >
            ← Prev
          </button>
          <span className="small muted">
            {total > 0 ? `${rangeStart}–${rangeEnd} of ${total}` : "—"}
          </span>
          <button
            className="small-btn"
            disabled={!hasNext}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            Next →
          </button>
        </div>
      </div>
    </>
  );
}

export default function AuditPage() {
  return (
    <Protected>
      <AuditInner />
    </Protected>
  );
}
