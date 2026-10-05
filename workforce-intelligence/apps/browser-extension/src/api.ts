/** Device-authenticated API client (runs in the background service worker). */
import { ExtConfig } from "./config";

export interface BrowserEventPayload {
  client_event_id: string;
  browser: string;
  domain: string;
  url: string; // already sanitized before reaching here
  page_title: string;
  started_at: string;
  ended_at: string;
  active_seconds: number;
  focused: boolean;
}

export interface ContentSnapshotPayload {
  client_event_id: string;
  source: string;
  domain: string;
  url: string; // sanitized
  content_type: string;
  external_reference?: string | null;
  content: string; // already redacted
  is_final: boolean;
  captured_at: string;
}

function headers(cfg: ExtConfig): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Device-Key": cfg.deviceKey,
    "X-Device-Secret": cfg.deviceSecret,
  };
}

async function post(cfg: ExtConfig, path: string, body: unknown): Promise<Response> {
  return fetch(cfg.apiBaseUrl.replace(/\/$/, "") + path, {
    method: "POST",
    headers: headers(cfg),
    body: JSON.stringify(body),
  });
}

export async function sendBrowserEvents(cfg: ExtConfig, events: BrowserEventPayload[]) {
  if (!events.length) return;
  await post(cfg, "/api/v1/agent/browser/batch", { events });
}

export async function sendContentSnapshots(cfg: ExtConfig, events: ContentSnapshotPayload[]) {
  if (!events.length) return;
  await post(cfg, "/api/v1/agent/content/batch", { events });
}

export async function sendHeartbeat(cfg: ExtConfig, idleSeconds: number) {
  await post(cfg, "/api/v1/agent/heartbeat", {
    reported_at: new Date().toISOString(),
    agent_version: "ext-0.1.0",
    idle_seconds: idleSeconds,
    is_locked: false,
  });
}

export interface CollectorConfig {
  allowlisted_domains: string[];
  content_debounce_seconds: number;
  heartbeat_seconds: number;
  batch_max: number;
}

export async function fetchCollectorConfig(cfg: ExtConfig): Promise<CollectorConfig | null> {
  try {
    const resp = await fetch(cfg.apiBaseUrl.replace(/\/$/, "") + "/api/v1/agent/config", {
      headers: headers(cfg),
    });
    if (!resp.ok) return null;
    // NOTE: this is DATA ONLY (allowlist + intervals). It is never executed.
    return (await resp.json()) as CollectorConfig;
  } catch {
    return null;
  }
}
