"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { isAdminRole, useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { RequireOrg } from "@/components/RequireOrg";
import { ErrorNotice, Loading } from "@/components/ui";
import { formatRelative } from "@/lib/format";
import type {
  Campaign,
  IntegrationChannel,
  IntegrationStatus,
} from "@/lib/types";

const CHANNELS: IntegrationChannel[] = ["meta", "google", "linkedin", "crm", "email"];

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function message(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function IntegrationsInner() {
  const { me, activeOrgId } = useAuth();
  const isSuper = me?.role === "SUPER_ADMIN";

  const [rows, setRows] = useState<IntegrationStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncNote, setSyncNote] = useState<string | null>(null);

  // Credential form state.
  const [channel, setChannel] = useState<IntegrationChannel>("meta");
  const [displayName, setDisplayName] = useState("");
  const [token, setToken] = useState("");
  const [config, setConfig] = useState('{\n  "ad_account_id": "123"\n}');
  const [credBusy, setCredBusy] = useState(false);
  const [credOk, setCredOk] = useState<string | null>(null);
  const [credErr, setCredErr] = useState<string | null>(null);

  // Campaigns state.
  const [campaignChannel, setCampaignChannel] = useState<string>("");
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [campaignErr, setCampaignErr] = useState<string | null>(null);

  // Org id used for path-scoped calls: the top-bar choice for SUPER_ADMIN,
  // otherwise the user's own org.
  const pathOrgId = activeOrgId ?? "";
  // Query param for reads: SUPER_ADMIN passes it, others omit.
  const readOrgParam = isSuper ? pathOrgId || undefined : undefined;

  const loadIntegrations = useCallback(
    (signal?: AbortSignal) => {
      setError(null);
      api
        .integrations(readOrgParam, signal)
        .then(setRows)
        .catch((err) => {
          if (isAbort(err)) return;
          if (err instanceof ApiError && err.status === 401) return;
          setError(message(err, "Failed to load integrations."));
        });
    },
    [readOrgParam]
  );

  useEffect(() => {
    const controller = new AbortController();
    loadIntegrations(controller.signal);
    return () => controller.abort();
  }, [loadIntegrations]);

  const loadCampaigns = useCallback(
    (signal?: AbortSignal) => {
      if (!pathOrgId) {
        setCampaigns([]);
        return;
      }
      setCampaignErr(null);
      api
        .campaigns(pathOrgId, campaignChannel || undefined, signal)
        .then(setCampaigns)
        .catch((err) => {
          if (isAbort(err)) return;
          if (err instanceof ApiError && err.status === 401) return;
          setCampaignErr(message(err, "Failed to load campaigns."));
        });
    },
    [pathOrgId, campaignChannel]
  );

  useEffect(() => {
    const controller = new AbortController();
    loadCampaigns(controller.signal);
    return () => controller.abort();
  }, [loadCampaigns]);

  async function saveCredential(e: FormEvent) {
    e.preventDefault();
    setCredOk(null);
    setCredErr(null);
    if (!pathOrgId) {
      setCredErr("Select an organization first.");
      return;
    }
    let parsedConfig: Record<string, unknown>;
    try {
      const raw = config.trim() ? JSON.parse(config) : {};
      if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
        throw new Error("Config must be a JSON object.");
      }
      parsedConfig = raw as Record<string, unknown>;
    } catch (err) {
      setCredErr(`Invalid config JSON: ${message(err, "could not parse.")}`);
      return;
    }
    setCredBusy(true);
    try {
      await api.setIntegrationCredential(pathOrgId, {
        channel,
        display_name: displayName.trim(),
        token,
        config: parsedConfig,
      });
      setCredOk(`Saved credentials for ${channel}.`);
      setToken("");
      loadIntegrations();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setCredErr(message(err, "Failed to save credentials."));
    } finally {
      setCredBusy(false);
    }
  }

  async function sync(ch: IntegrationChannel) {
    setSyncNote(null);
    if (!pathOrgId) {
      setError("Select an organization first.");
      return;
    }
    setSyncing(ch);
    try {
      const res = await api.syncIntegration(pathOrgId, ch);
      setSyncNote(`Synced ${ch}: ${res.synced} record${res.synced === 1 ? "" : "s"}.`);
      loadIntegrations();
      loadCampaigns();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(message(err, `Failed to sync ${ch}.`));
    } finally {
      setSyncing(null);
    }
  }

  if (!me) return <Loading label="Loading your profile…" />;

  if (!isAdminRole(me.role)) {
    return (
      <>
        <h1 className="page-title">Integrations</h1>
        <ErrorNotice message="You are not authorized to view this page." />
      </>
    );
  }

  return (
    <>
      <h1 className="page-title">Integrations</h1>
      <p className="page-sub">
        Connect advertising, CRM and email channels to enrich session attribution.
      </p>

      {error ? <ErrorNotice message={error} /> : null}

      <div className="card">
        <div className="card-head">
          <h2>Channels</h2>
          {syncNote ? <span className="small" style={{ color: "var(--green)" }}>{syncNote}</span> : null}
        </div>
        {!rows ? (
          <Loading />
        ) : rows.length === 0 ? (
          <div className="notice">No integration channels available.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Channel</th>
                  <th>Name</th>
                  <th>Configured</th>
                  <th>Active</th>
                  <th>Last synced</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.channel}>
                    <td>
                      <strong>{r.channel}</strong>
                    </td>
                    <td className="muted">{r.display_name || "—"}</td>
                    <td>{r.configured ? "Yes" : "No"}</td>
                    <td className={r.is_active ? "" : "muted"}>{r.is_active ? "Yes" : "No"}</td>
                    <td className="muted small">{formatRelative(r.last_synced_at)}</td>
                    <td>
                      <button
                        className="small-btn"
                        disabled={syncing !== null || !r.configured}
                        onClick={() => sync(r.channel)}
                      >
                        {syncing === r.channel ? "Syncing…" : "Sync"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Set credential</h2>
        <form onSubmit={saveCredential}>
          <div className="row" style={{ marginBottom: 0 }}>
            <div className="field" style={{ flex: "1 1 160px" }}>
              <label htmlFor="cred-channel">Channel</label>
              <select
                id="cred-channel"
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: "1 1 220px" }}>
              <label htmlFor="cred-name">Display name</label>
              <input
                id="cred-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Acme Meta Ads"
                required
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="cred-token">Token (secret)</label>
            <input
              id="cred-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="access token"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="cred-config">Config (JSON object)</label>
            <textarea
              id="cred-config"
              className="mono"
              rows={4}
              value={config}
              onChange={(e) => setConfig(e.target.value)}
            />
          </div>
          <button className="primary" type="submit" disabled={credBusy}>
            {credBusy ? "Saving…" : "Save credential"}
          </button>
          {credErr ? (
            <div className="notice error" style={{ marginTop: 12 }}>
              {credErr}
            </div>
          ) : null}
          {credOk ? (
            <div
              className="notice"
              style={{
                marginTop: 12,
                color: "var(--green)",
                borderColor: "rgba(63, 182, 127, 0.4)",
                background: "rgba(63, 182, 127, 0.08)",
              }}
            >
              {credOk}
            </div>
          ) : null}
        </form>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Campaigns</h2>
          <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
            <label htmlFor="camp-channel" style={{ marginBottom: 4 }}>
              Filter by channel
            </label>
            <select
              id="camp-channel"
              value={campaignChannel}
              onChange={(e) => setCampaignChannel(e.target.value)}
            >
              <option value="">All channels</option>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>

        {campaignErr ? (
          <ErrorNotice message={campaignErr} />
        ) : !campaigns ? (
          <Loading />
        ) : campaigns.length === 0 ? (
          <div className="notice">No campaigns for this selection.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Channel</th>
                  <th>External id</th>
                  <th>Status</th>
                  <th>Synced</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                    </td>
                    <td className="muted">{c.channel}</td>
                    <td className="mono small">{c.external_id}</td>
                    <td className="muted">{c.status}</td>
                    <td className="muted small">{formatRelative(c.synced_at)}</td>
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

export default function IntegrationsPage() {
  return (
    <Protected>
      <RequireOrg>
        <IntegrationsInner />
      </RequireOrg>
    </Protected>
  );
}
