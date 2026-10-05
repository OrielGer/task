"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { isAdminRole, useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { RequireOrg } from "@/components/RequireOrg";
import { Empty, ErrorNotice, Loading } from "@/components/ui";
import { formatDateTime, formatDuration, formatRelative } from "@/lib/format";
import type {
  AgentRun,
  AgentRunStatus,
  AgentSuggestion,
  AutomationAgent,
  AutomationTemplates,
} from "@/lib/types";

const CHANNEL_LABELS: Record<string, string> = {
  meta: "Meta Ads",
  google: "Google Ads",
  linkedin: "LinkedIn Ads",
  crm: "HubSpot CRM",
  email: "Email",
};

const STEP_ICON: Record<string, string> = { done: "✓", skipped: "–", failed: "✕" };

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function message(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function RunStatusBadge({ status }: { status: AgentRunStatus }) {
  const map: Record<string, [string, string]> = {
    awaiting_approval: ["sev-medium", "Awaiting approval"],
    approved: ["status-active", "Approved"],
    rejected: ["status-offline", "Rejected"],
    failed: ["sev-high", "Failed"],
  };
  const [cls, label] = map[status] ?? ["sev-low", status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — the text can be selected manually */
    }
  }
  return (
    <button type="button" className="small-btn" onClick={copy}>
      {copied ? "Copied" : "Copy draft"}
    </button>
  );
}

function RunView({
  run,
  canManage,
  busy,
  onReview,
}: {
  run: AgentRun;
  canManage: boolean;
  busy: boolean;
  onReview: (run: AgentRun, decision: "approve" | "reject") => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: 14,
        marginBottom: 12,
      }}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <RunStatusBadge status={run.status} />
          <span className="small muted">{formatDateTime(run.started_at)}</span>
          {run.sandbox ? <span className="badge sev-low">Sandbox data</span> : null}
          <span className="small faint">AI: {run.provider}</span>
        </div>
        {run.minutes_saved > 0 ? (
          <span className="small" style={{ color: "var(--green)" }}>
            Saved {formatDuration(run.minutes_saved * 60)}
          </span>
        ) : null}
      </div>

      <ul className="small muted" style={{ margin: "10px 0", paddingLeft: 18 }}>
        {run.steps.map((s, i) => (
          <li key={i}>
            {STEP_ICON[s.status] ?? "•"} {s.name}
            {s.detail ? ` — ${s.detail}` : ""}
          </li>
        ))}
      </ul>

      {run.output ? (
        <pre
          style={{
            whiteSpace: "pre-wrap",
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 12,
            fontSize: 13,
            margin: "10px 0",
          }}
        >
          {run.output}
        </pre>
      ) : null}

      <div className="row">
        {run.output ? <CopyButton value={run.output} /> : null}
        {canManage && run.status === "awaiting_approval" ? (
          <>
            <button
              type="button"
              className="small-btn primary"
              disabled={busy}
              onClick={() => onReview(run, "approve")}
            >
              Approve
            </button>
            <button
              type="button"
              className="small-btn ghost"
              disabled={busy}
              onClick={() => onReview(run, "reject")}
            >
              Reject
            </button>
            <span className="small faint">
              Approving records the time saved. Nothing is sent or changed automatically; use
              the draft where it is needed.
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}

function AutomationInner() {
  const { me } = useAuth();
  const canManage = isAdminRole(me?.role);

  const [meta, setMeta] = useState<AutomationTemplates | null>(null);
  const [agents, setAgents] = useState<AutomationAgent[] | null>(null);
  const [suggestions, setSuggestions] = useState<AgentSuggestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [runs, setRuns] = useState<AgentRun[] | null>(null);

  const onLoadError = useCallback((err: unknown) => {
    if (isAbort(err)) return;
    if (err instanceof ApiError && err.status === 401) return;
    setError(message(err, "Failed to load automation agents."));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const loads: Promise<unknown>[] = [
      api.automationTemplates(controller.signal).then(setMeta),
      api.automationAgents(controller.signal).then(setAgents),
    ];
    if (canManage) loads.push(api.automationSuggestions(controller.signal).then(setSuggestions));
    Promise.all(loads).catch(onLoadError);
    return () => controller.abort();
  }, [canManage, onLoadError]);

  const reloadAgents = useCallback(async () => {
    setAgents(await api.automationAgents());
  }, []);

  const reloadRuns = useCallback(async (agentId: string) => {
    setRuns(await api.automationAgentRuns(agentId));
  }, []);

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    setNote(null);
    try {
      await fn();
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        setError(message(err, "The action failed."));
      }
    } finally {
      setBusy(null);
    }
  }

  const templateName = (key: string) => meta?.templates.find((t) => t.key === key)?.name ?? key;

  function createAgent(template: string, sourceWorkflow?: string) {
    void act(`create:${template}:${sourceWorkflow ?? ""}`, async () => {
      const agent = await api.createAutomationAgent({
        template,
        source_workflow: sourceWorkflow ?? null,
      });
      await reloadAgents();
      if (canManage) setSuggestions(await api.automationSuggestions());
      setSelected(agent.id);
      setRuns([]);
      setNote(`Created “${agent.name}”. Click “Run now” to get its first draft.`);
    });
  }

  function runAgent(agent: AutomationAgent) {
    void act(`run:${agent.id}`, async () => {
      const run = await api.runAutomationAgent(agent.id);
      setSelected(agent.id);
      await Promise.all([reloadAgents(), reloadRuns(agent.id)]);
      setNote(
        run.status === "failed"
          ? "The run could not read any data. Its steps below explain why."
          : "Draft ready. Review it below."
      );
    });
  }

  function toggleAgent(agent: AutomationAgent) {
    void act(`toggle:${agent.id}`, async () => {
      await api.updateAutomationAgent(agent.id, {
        status: agent.status === "active" ? "paused" : "active",
      });
      await reloadAgents();
    });
  }

  function showRuns(agentId: string) {
    setSelected(agentId);
    setRuns(null);
    reloadRuns(agentId).catch(onLoadError);
  }

  function review(run: AgentRun, decision: "approve" | "reject") {
    void act(`review:${run.id}`, async () => {
      await api.reviewAgentRun(run.id, decision);
      await Promise.all([reloadAgents(), reloadRuns(run.agent_id)]);
    });
  }

  if (!me || !agents || !meta) {
    return error ? <ErrorNotice message={error} /> : <Loading />;
  }

  const totalMinutes = agents.reduce((sum, a) => sum + a.minutes_saved, 0);
  const awaiting = agents.reduce((sum, a) => sum + a.awaiting_approval, 0);
  const selectedAgent = agents.find((a) => a.id === selected) ?? null;

  return (
    <>
      <h1 className="page-title">Automation agents</h1>
      <p className="page-sub">
        Agents prepare recurring work (reports, status emails, proposed changes) from your connected
        systems. A person approves every run. Agents never change anything in external systems or
        on employees&apos; computers.
      </p>

      {meta.integration_mode === "sandbox" || meta.ai_provider === "mock" ? (
        <div className="notice" style={{ marginBottom: 16 }}>
          {meta.integration_mode === "sandbox"
            ? "Sandbox mode: agents read sample campaign data. Connect your integrations and set INTEGRATION_MODE=live to use real data. "
            : ""}
          {meta.ai_provider === "mock"
            ? "No AI provider is configured, so drafts are assembled from the data without AI rewriting."
            : ""}
        </div>
      ) : null}

      {error ? (
        <div style={{ marginBottom: 16 }}>
          <ErrorNotice message={error} />
        </div>
      ) : null}
      {note ? (
        <div
          className="notice"
          style={{
            marginBottom: 16,
            color: "var(--green)",
            borderColor: "rgba(63, 182, 127, 0.4)",
            background: "rgba(63, 182, 127, 0.08)",
          }}
        >
          {note}
        </div>
      ) : null}

      <div className="stats">
        <div className="stat">
          <div className="n">{agents.length}</div>
          <div className="l">Agents</div>
        </div>
        <div className="stat">
          <div className="n" style={{ color: awaiting ? "var(--amber)" : undefined }}>{awaiting}</div>
          <div className="l">Awaiting approval</div>
        </div>
        <div className="stat">
          <div className="n" style={{ color: "var(--green)" }}>{formatDuration(totalMinutes * 60)}</div>
          <div className="l">Time saved (approved runs)</div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Your agents</h2>
        </div>
        {agents.length === 0 ? (
          <Empty>No agents yet. Create one from a suggestion or a template below.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Runs</th>
                  <th>Awaiting</th>
                  <th>Time saved</th>
                  <th>Last run</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <strong>{a.name}</strong>
                      <div className="faint small">
                        {templateName(a.template)}
                        {a.source_workflow ? ` · from “${a.source_workflow}”` : ""}
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${a.status === "active" ? "status-active" : "status-offline"}`}>
                        {a.status === "active" ? "Active" : "Paused"}
                      </span>
                    </td>
                    <td>{a.runs}</td>
                    <td>{a.awaiting_approval}</td>
                    <td>{formatDuration(a.minutes_saved * 60)}</td>
                    <td className="muted small">{a.last_run_at ? formatRelative(a.last_run_at) : "—"}</td>
                    <td>
                      <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                        {canManage ? (
                          <>
                            <button
                              type="button"
                              className="small-btn primary"
                              disabled={busy !== null || a.status !== "active"}
                              onClick={() => runAgent(a)}
                            >
                              {busy === `run:${a.id}` ? "Running…" : "Run now"}
                            </button>
                            <button
                              type="button"
                              className="small-btn ghost"
                              disabled={busy !== null}
                              onClick={() => toggleAgent(a)}
                            >
                              {a.status === "active" ? "Pause" : "Resume"}
                            </button>
                          </>
                        ) : null}
                        <button type="button" className="small-btn" onClick={() => showRuns(a.id)}>
                          Runs
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedAgent ? (
        <div className="card">
          <div className="card-head">
            <h2>Runs · {selectedAgent.name}</h2>
            <button type="button" className="small-btn ghost" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          {runs === null ? (
            <Loading />
          ) : runs.length === 0 ? (
            <Empty>No runs yet.</Empty>
          ) : (
            runs.map((r) => (
              <RunView
                key={r.id}
                run={r}
                canManage={canManage}
                busy={busy === `review:${r.id}`}
                onReview={review}
              />
            ))
          )}
        </div>
      ) : null}

      {canManage ? (
        <div className="card">
          <div className="card-head">
            <h2>Suggested from your team&apos;s work</h2>
          </div>
          {!suggestions ? (
            <Loading />
          ) : suggestions.length === 0 ? (
            <Empty>
              No repetitive workflows that an agent can take over yet. Suggestions appear after the
              collectors have gathered a few days of activity (see Analytics → Automation).
            </Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Repeated workflow</th>
                    <th>Per week</th>
                    <th>Potential saving / week</th>
                    <th>Suggested agent</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {suggestions.map((s) => (
                    <tr key={s.workflow_name}>
                      <td>{s.workflow_name}</td>
                      <td>{s.occurrences_per_week}×</td>
                      <td>{formatDuration(s.potential_weekly_savings_seconds)}</td>
                      <td>{templateName(s.suggested_template)}</td>
                      <td>
                        {s.has_agent ? (
                          <span className="small faint">Agent exists</span>
                        ) : (
                          <button
                            type="button"
                            className="small-btn primary"
                            disabled={busy !== null}
                            onClick={() => createAgent(s.suggested_template, s.workflow_name)}
                          >
                            Create agent
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      <div className="card">
        <div className="card-head">
          <h2>Templates</h2>
        </div>
        <div className="section-grid cols-2">
          {meta.templates.map((t) => (
            <div
              key={t.key}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: 14,
              }}
            >
              <strong>{t.name}</strong>
              <p className="muted small" style={{ margin: "6px 0 10px" }}>
                {t.description}
              </p>
              <div className="faint small" style={{ marginBottom: 10 }}>
                Reads: {t.channels.map((c) => CHANNEL_LABELS[c] ?? c).join(", ")} · saves about{" "}
                {t.minutes_saved_per_run} min per run
              </div>
              {canManage ? (
                <button
                  type="button"
                  className="small-btn"
                  disabled={busy !== null}
                  onClick={() => createAgent(t.key)}
                >
                  {busy === `create:${t.key}:` ? "Creating…" : "Create agent"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default function AutomationPage() {
  return (
    <Protected>
      <RequireOrg>
        <AutomationInner />
      </RequireOrg>
    </Protected>
  );
}
