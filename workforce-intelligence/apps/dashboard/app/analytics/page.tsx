"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { Protected } from "@/components/Protected";
import { RequireOrg } from "@/components/RequireOrg";
import { ErrorNotice, Loading, UsageBars } from "@/components/ui";
import { formatDuration, formatPercent } from "@/lib/format";
import type { AutomationOpportunity, UsageRow, WorkflowRow } from "@/lib/types";

type Tab = "apps" | "websites" | "workflows" | "automation";

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function AnalyticsInner() {
  const [tab, setTab] = useState<Tab>("apps");
  const [apps, setApps] = useState<UsageRow[] | null>(null);
  const [websites, setWebsites] = useState<UsageRow[] | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowRow[] | null>(null);
  const [automation, setAutomation] = useState<AutomationOpportunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    const onErr = (err: unknown) => {
      if (isAbort(err)) return;
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Failed to load analytics.");
    };
    Promise.all([
      api.analyticsApps({}, controller.signal).then(setApps).catch(onErr),
      api.analyticsWebsites({}, controller.signal).then(setWebsites).catch(onErr),
      api.analyticsWorkflows({}, controller.signal).then(setWorkflows).catch(onErr),
      api
        .analyticsAutomation({}, controller.signal)
        .then(setAutomation)
        .catch(onErr),
    ]);
    return () => controller.abort();
  }, []);

  return (
    <>
      <h1 className="page-title">Organization analytics</h1>
      <p className="page-sub">
        Aggregated application, website, and repetitive-workflow usage across your team.
      </p>

      <div className="tabs">
        <button className={`tab${tab === "apps" ? " active" : ""}`} onClick={() => setTab("apps")}>
          Applications
        </button>
        <button
          className={`tab${tab === "websites" ? " active" : ""}`}
          onClick={() => setTab("websites")}
        >
          Websites
        </button>
        <button
          className={`tab${tab === "workflows" ? " active" : ""}`}
          onClick={() => setTab("workflows")}
        >
          Workflows
        </button>
        <button
          className={`tab${tab === "automation" ? " active" : ""}`}
          onClick={() => setTab("automation")}
        >
          Automation
        </button>
      </div>

      {error ? <ErrorNotice message={error} /> : null}

      {tab === "apps" ? (
        <div className="card">
          <h2>Application usage</h2>
          {!apps ? <Loading /> : <UsageBars rows={apps} />}
        </div>
      ) : null}

      {tab === "websites" ? (
        <div className="card">
          <h2>Website usage</h2>
          {!websites ? <Loading /> : <UsageBars rows={websites} />}
        </div>
      ) : null}

      {tab === "workflows" ? (
        <div className="card">
          <h2>Repetitive workflows</h2>
          {!workflows ? (
            <Loading />
          ) : workflows.length === 0 ? (
            <div className="notice">No repetitive workflows detected for this range.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Occurrences / week</th>
                    <th>Avg duration</th>
                    <th>Employees</th>
                    <th>Automation score</th>
                    <th>Potential weekly saving</th>
                  </tr>
                </thead>
                <tbody>
                  {workflows.map((w, i) => (
                    <tr key={`${w.workflow_name}-${i}`}>
                      <td>
                        <strong>{w.workflow_name}</strong>
                      </td>
                      <td>{w.occurrences_per_week}</td>
                      <td>{formatDuration(w.average_seconds)}</td>
                      <td className="muted">{w.employees?.length ?? 0}</td>
                      <td>{formatPercent(w.automation_score)}</td>
                      <td>{formatDuration(w.potential_weekly_savings_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {tab === "automation" ? (
        <div className="card">
          <h2>Automation opportunities</h2>
          <p className="muted small" style={{ marginBottom: 14 }}>
            Repetitive workflows ranked by how readily they could be automated and
            the time that would be freed up each week.
          </p>
          {!automation ? (
            <Loading />
          ) : automation.length === 0 ? (
            <div className="notice">No automation opportunities detected for this range.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Occurrences / week</th>
                    <th>Avg duration</th>
                    <th>Employees</th>
                    <th>Automation score</th>
                    <th>Potential weekly saving</th>
                  </tr>
                </thead>
                <tbody>
                  {automation.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <strong>{a.workflow_name}</strong>
                      </td>
                      <td>{a.occurrences_per_week}</td>
                      <td>{formatDuration(a.average_seconds)}</td>
                      <td className="muted">{a.employees?.length ?? 0}</td>
                      <td>{formatPercent(a.automation_score)}</td>
                      <td>{formatDuration(a.potential_weekly_savings_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}

export default function AnalyticsPage() {
  return (
    <Protected>
      <RequireOrg>
        <AnalyticsInner />
      </RequireOrg>
    </Protected>
  );
}
