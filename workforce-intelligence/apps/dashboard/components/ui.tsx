"use client";

import type { ReactNode } from "react";

import { formatDuration } from "@/lib/format";
import type { EmployeeStatus, InsightSeverity, UsageRow } from "@/lib/types";

export function StatusBadge({ status }: { status: EmployeeStatus }) {
  const s = (status || "").toLowerCase();
  const cls =
    s === "active"
      ? "status-active"
      : s === "idle"
        ? "status-idle"
        : "status-offline";
  const label = s ? s[0].toUpperCase() + s.slice(1) : "Unknown";
  return <span className={`badge badge-dot ${cls}`}>{label}</span>;
}

export function SeverityBadge({ severity }: { severity: InsightSeverity }) {
  const s = (severity || "").toLowerCase();
  const cls =
    s === "critical"
      ? "sev-critical"
      : s === "high"
        ? "sev-high"
        : s === "medium"
          ? "sev-medium"
          : "sev-low";
  const label = s ? s[0].toUpperCase() + s.slice(1) : "Info";
  return <span className={`badge ${cls}`}>{label}</span>;
}

/** Horizontal usage bars, normalized to the largest active_seconds value. */
export function UsageBars({ rows }: { rows: UsageRow[] }) {
  if (rows.length === 0) return <Empty>No usage recorded for this range.</Empty>;
  const max = Math.max(...rows.map((r) => r.active_seconds), 1);
  return (
    <div>
      {rows.map((r, i) => (
        <div className="bar-row" key={`${r.label}-${i}`}>
          <div className="bar-label" title={r.label}>
            {r.label || "(unlabeled)"}
          </div>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${Math.max(2, (r.active_seconds / max) * 100)}%` }}
            />
          </div>
          <div className="bar-value">
            {formatDuration(r.active_seconds)} · {r.event_count}×
          </div>
        </div>
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>;
}

export function ErrorNotice({ message }: { message: string }) {
  return <div className="notice error">{message}</div>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="loading">{label}</div>;
}
