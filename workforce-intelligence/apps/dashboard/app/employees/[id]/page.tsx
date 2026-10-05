"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";
import { Protected } from "@/components/Protected";
import { ContentPanel } from "@/components/ContentPanel";
import {
  Empty,
  ErrorNotice,
  Loading,
  SeverityBadge,
  StatusBadge,
  UsageBars,
} from "@/components/ui";
import {
  formatDuration,
  formatRelative,
  formatTimeRange,
  nextISODate,
  splitCsv,
  todayISODate,
} from "@/lib/format";
import type {
  AIInsight,
  AISummary,
  CurrentActivity,
  Employee,
  TimelineEntry,
  UsageRow,
  WorkSession,
} from "@/lib/types";

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function EmployeeInner({ id }: { id: string }) {
  const [date, setDate] = useState<string>(todayISODate());

  const [employee, setEmployee] = useState<Employee | null>(null);
  const [employeeErr, setEmployeeErr] = useState<string | null>(null);
  const [current, setCurrent] = useState<CurrentActivity | null>(null);

  const [timeline, setTimeline] = useState<TimelineEntry[] | null>(null);
  const [apps, setApps] = useState<UsageRow[] | null>(null);
  const [websites, setWebsites] = useState<UsageRow[] | null>(null);
  const [sessions, setSessions] = useState<WorkSession[] | null>(null);
  const [insights, setInsights] = useState<AIInsight[] | null>(null);
  const [summary, setSummary] = useState<AISummary | null>(null);
  const [summaryErr, setSummaryErr] = useState<string | null>(null);
  const [rangeErr, setRangeErr] = useState<string | null>(null);

  // Employee record (date-independent).
  useEffect(() => {
    const controller = new AbortController();
    api
      .employee(id, controller.signal)
      .then(setEmployee)
      .catch((err) => {
        if (isAbort(err)) return;
        if (err instanceof ApiError && err.status === 401) return;
        setEmployeeErr(err instanceof Error ? err.message : "Failed to load employee.");
      });
    return () => controller.abort();
  }, [id]);

  // Current activity (most recent focus interval; date-independent).
  useEffect(() => {
    const controller = new AbortController();
    api
      .currentActivity(id, controller.signal)
      .then(setCurrent)
      .catch(() => {
        /* non-critical widget; ignore load errors */
      });
    return () => controller.abort();
  }, [id]);

  // Date-scoped data.
  const loadRange = useCallback(
    (signal: AbortSignal) => {
      const range = { start: date, end: nextISODate(date) };
      setTimeline(null);
      setApps(null);
      setWebsites(null);
      setSessions(null);
      setInsights(null);
      setSummary(null);
      setSummaryErr(null);
      setRangeErr(null);

      const onErr = (err: unknown) => {
        if (isAbort(err)) return;
        if (err instanceof ApiError && err.status === 401) return;
        setRangeErr(err instanceof Error ? err.message : "Failed to load activity.");
      };

      api.timeline(id, range, signal).then(setTimeline).catch(onErr);
      api.applications(id, range, signal).then(setApps).catch(onErr);
      api.websites(id, range, signal).then(setWebsites).catch(onErr);
      api.sessions(id, range, signal).then(setSessions).catch(onErr);
      api.insights(id, range, signal).then(setInsights).catch(onErr);
      api
        .summary(id, date, signal)
        .then(setSummary)
        .catch((err) => {
          if (isAbort(err)) return;
          if (err instanceof ApiError && err.status === 401) return;
          setSummaryErr(err instanceof Error ? err.message : "No summary available.");
        });
    },
    [id, date]
  );

  useEffect(() => {
    const controller = new AbortController();
    loadRange(controller.signal);
    return () => controller.abort();
  }, [loadRange]);

  return (
    <>
      <p className="small" style={{ marginBottom: 8 }}>
        <Link href="/">← Overview</Link>
      </p>

      {employeeErr ? (
        <ErrorNotice message={employeeErr} />
      ) : !employee ? (
        <Loading />
      ) : (
        <div className="card-head" style={{ marginBottom: 16 }}>
          <div>
            <h1 className="page-title">{employee.display_name}</h1>
            <p className="page-sub" style={{ marginBottom: 0 }}>
              {employee.email} · last seen {formatRelative(employee.last_seen_at)}
            </p>
          </div>
          <StatusBadge status={employee.status} />
        </div>
      )}

      {current && current.label ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <p className="small muted" style={{ marginBottom: 2 }}>
                {current.is_live ? "Currently working on" : "Last worked on"}
              </p>
              <strong>{current.label}</strong>
              {current.detail ? <span className="muted"> — {current.detail}</span> : null}
              {current.since ? (
                <p className="small muted" style={{ marginTop: 2, marginBottom: 0 }}>
                  since {formatRelative(current.since)}
                </p>
              ) : null}
            </div>
            <span className={`badge ${current.is_live ? "badge-active" : ""}`}>
              {current.is_live ? "live" : current.kind ?? ""}
            </span>
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <label htmlFor="date" style={{ marginBottom: 2 }}>
              Viewing day
            </label>
            <input
              id="date"
              type="date"
              value={date}
              max={todayISODate()}
              onChange={(e) => setDate(e.target.value || todayISODate())}
              style={{ width: 180 }}
            />
          </div>
          <div className="small muted">
            Showing activity for {date}. Durations are active time.
          </div>
        </div>
      </div>

      {rangeErr ? <ErrorNotice message={rangeErr} /> : null}

      {/* Daily timeline */}
      <div className="card">
        <h2>Daily timeline</h2>
        {!timeline ? (
          <Loading />
        ) : timeline.length === 0 ? (
          <Empty>No activity recorded on this day.</Empty>
        ) : (
          <div>
            {timeline.map((t, i) => (
              <div className="timeline-row" key={i}>
                <div className="timeline-time">{formatTimeRange(t.started_at, t.ended_at)}</div>
                <div className="timeline-time">{formatDuration(t.active_seconds)}</div>
                <div>
                  <span className="timeline-label">{t.label || "(unlabeled)"}</span>{" "}
                  <span className="badge sev-low" style={{ marginLeft: 6 }}>
                    {t.kind}
                  </span>
                  {t.detail ? <div className="timeline-detail">{t.detail}</div> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section-grid cols-2">
        <div className="card">
          <h2>Application usage</h2>
          {!apps ? <Loading /> : <UsageBars rows={apps} />}
        </div>
        <div className="card">
          <h2>Website usage</h2>
          {!websites ? <Loading /> : <UsageBars rows={websites} />}
        </div>
      </div>

      {/* Work sessions */}
      <div className="card">
        <h2>Work sessions</h2>
        {!sessions ? (
          <Loading />
        ) : sessions.length === 0 ? (
          <Empty>No work sessions on this day.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Active</th>
                  <th>Apps</th>
                  <th>Domains</th>
                  <th>Inferred context</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id}>
                    <td className="mono small">{formatTimeRange(s.started_at, s.ended_at)}</td>
                    <td>{formatDuration(s.active_seconds)}</td>
                    <td className="small">{splitCsv(s.apps).join(", ") || "—"}</td>
                    <td className="small">{splitCsv(s.domains).join(", ") || "—"}</td>
                    <td className="small">
                      {s.inferred_customer ? (
                        <div>
                          <span className="muted">Customer:</span> {s.inferred_customer}
                        </div>
                      ) : null}
                      {s.inferred_campaign ? (
                        <div>
                          <span className="muted">Campaign:</span> {s.inferred_campaign}
                        </div>
                      ) : null}
                      {s.inferred_task ? (
                        <div>
                          <span className="muted">Task:</span> {s.inferred_task}
                        </div>
                      ) : null}
                      {!s.inferred_customer && !s.inferred_campaign && !s.inferred_task ? "—" : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* AI summary */}
      <div className="card">
        <h2>AI summary ({date})</h2>
        {summary ? (
          <>
            <p style={{ marginTop: 0, whiteSpace: "pre-wrap" }}>{summary.summary}</p>
            <div className="small faint">provider: {summary.provider}</div>
          </>
        ) : summaryErr ? (
          <Empty>{summaryErr}</Empty>
        ) : (
          <Loading />
        )}
      </div>

      {/* AI recommendations / insights */}
      <div className="card">
        <h2>AI recommendations</h2>
        {!insights ? (
          <Loading />
        ) : insights.length === 0 ? (
          <Empty>No insights for this range.</Empty>
        ) : (
          <div className="section-grid">
            {insights.map((ins) => (
              <div
                key={ins.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: "12px 14px",
                }}
              >
                <div className="card-head" style={{ marginBottom: 8 }}>
                  <strong>{ins.title}</strong>
                  <SeverityBadge severity={ins.severity} />
                </div>
                {ins.detail ? <p className="small" style={{ marginTop: 0 }}>{ins.detail}</p> : null}
                {ins.recommendation ? (
                  <p className="small" style={{ marginBottom: 0 }}>
                    <span className="muted">Recommendation:</span> {ins.recommendation}
                  </p>
                ) : null}
                <div className="small faint" style={{ marginTop: 6 }}>
                  {ins.kind}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Business content + version history */}
      <div className="card">
        <h2>Business content</h2>
        <ContentPanel employeeId={id} />
      </div>
    </>
  );
}

export default function EmployeePage({ params }: { params: { id: string } }) {
  return (
    <Protected>
      <EmployeeInner id={params.id} />
    </Protected>
  );
}
