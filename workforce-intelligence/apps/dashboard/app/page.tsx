"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { RequireOrg } from "@/components/RequireOrg";
import { ErrorNotice, Loading, StatusBadge } from "@/components/ui";
import { formatRelative } from "@/lib/format";
import type { Employee } from "@/lib/types";

function activityHint(e: Employee): string {
  const s = (e.status || "").toLowerCase();
  if (s === "active") return "Active now";
  if (s === "idle") return "Idle";
  if (s === "offline") return "Offline";
  return "Unknown";
}

function OverviewInner() {
  const { me } = useAuth();
  const [employees, setEmployees] = useState<Employee[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .employees(controller.signal)
      .then(setEmployees)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load employees.");
      });
    return () => controller.abort();
  }, []);

  const counts = {
    active: employees?.filter((e) => e.status?.toLowerCase() === "active").length ?? 0,
    idle: employees?.filter((e) => e.status?.toLowerCase() === "idle").length ?? 0,
    offline: employees?.filter((e) => e.status?.toLowerCase() === "offline").length ?? 0,
  };

  return (
    <>
      <h1 className="page-title">Organization overview</h1>
      <p className="page-sub">
        {me ? (
          <>
            Signed in as {me.full_name || me.email}
            {me.organization_id ? ` · org ${me.organization_id}` : ""}
          </>
        ) : (
          "Team activity at a glance."
        )}
      </p>

      <div className="stats">
        <div className="stat">
          <div className="n" style={{ color: "var(--green)" }}>{counts.active}</div>
          <div className="l">Active</div>
        </div>
        <div className="stat">
          <div className="n" style={{ color: "var(--amber)" }}>{counts.idle}</div>
          <div className="l">Idle</div>
        </div>
        <div className="stat">
          <div className="n" style={{ color: "var(--text-faint)" }}>{counts.offline}</div>
          <div className="l">Offline</div>
        </div>
        <div className="stat">
          <div className="n">{employees?.length ?? 0}</div>
          <div className="l">Total employees</div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Employees</h2>
          <div className="row small">
            <Link href="/analytics">Analytics →</Link>
            <Link href="/ai">AI assistant →</Link>
          </div>
        </div>

        {error ? (
          <ErrorNotice message={error} />
        ) : !employees ? (
          <Loading />
        ) : employees.length === 0 ? (
          <div className="notice">No employees are visible for your role.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Activity</th>
                  <th>Last seen</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {employees.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <Link href={`/employees/${e.id}`}>
                        <strong>{e.display_name}</strong>
                      </Link>
                      <div className="faint small">{e.email}</div>
                    </td>
                    <td>
                      <StatusBadge status={e.status} />
                    </td>
                    <td className="muted">{activityHint(e)}</td>
                    <td className="muted small">{formatRelative(e.last_seen_at)}</td>
                    <td>
                      <Link href={`/employees/${e.id}`}>View →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

export default function OverviewPage() {
  return (
    <Protected>
      <RequireOrg>
        <OverviewInner />
      </RequireOrg>
    </Protected>
  );
}
