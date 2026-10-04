/**
 * Canonical wire types for the Workforce Intelligence platform.
 *
 * These mirror the backend Pydantic schemas (apps/api/app/schemas) and the
 * event examples in the spec. Collectors (browser extension) and the dashboard
 * import from here so the contract stays in one place.
 *
 * Reminder (see SECURITY.md): collectors send OUTBOUND metadata only. There is
 * no inbound command type in this file on purpose — the backend never pushes
 * executable instructions to a workstation.
 */

export type Role = "SUPER_ADMIN" | "ORG_ADMIN" | "MANAGER" | "EMPLOYEE";

export type EmployeeStatus = "active" | "idle" | "offline";

/** Active application/window focus interval reported by the Windows agent. */
export interface ActivityEvent {
  /** Client-generated idempotency key for safe batch retries. */
  client_event_id: string;
  application: string; // e.g. "Code.exe"
  window_title: string; // e.g. "campaign-analysis.py - marketing-tools"
  started_at: string; // ISO-8601
  ended_at: string; // ISO-8601
  active_seconds: number;
  is_idle: boolean;
  /** True while the workstation session is locked. */
  is_locked: boolean;
}

/** Active browser-tab visit reported by the extension (active tab only). */
export interface BrowserEvent {
  client_event_id: string;
  browser: "chrome" | "edge" | string;
  domain: string;
  /** URL AFTER local sanitization (sensitive query params stripped). */
  url: string;
  page_title: string;
  started_at: string;
  ended_at: string;
  active_seconds: number;
  /** Whether the browser window was focused for this interval. */
  focused: boolean;
}

export type ContentSource =
  | "crm"
  | "hubspot"
  | "meta_ads"
  | "google_ads"
  | "linkedin_ads"
  | "google_docs"
  | "cms"
  | "ai_tool"
  | "other";

/** A business-text snapshot from an allowlisted editor (already redacted). */
export interface ContentSnapshot {
  client_event_id: string;
  source: ContentSource;
  domain: string;
  /** Sanitized URL of the page the editor lives on. */
  url: string;
  content_type: string; // e.g. "ad_copy", "email", "doc"
  /** Stable reference to the logical item (e.g. doc id), when available. */
  external_reference?: string | null;
  /** Redacted text content of the editor at snapshot time. */
  content: string;
  /** True when captured on a recognized Save/Publish/Send/Submit action. */
  is_final: boolean;
  captured_at: string;
}

export interface AgentHeartbeat {
  reported_at: string;
  agent_version: string;
  /** Seconds since last user input, for idle computation on the server. */
  idle_seconds: number;
  is_locked: boolean;
}

export interface EventBatch<T> {
  device_id: string;
  events: T[];
}

/** Non-executable config the backend may return to a collector. Data only. */
export interface CollectorConfig {
  /** Domains on which business-text capture is permitted. */
  allowlisted_domains: string[];
  /** Debounce window (seconds) before snapshotting edits. */
  content_debounce_seconds: number;
  /** Heartbeat interval (seconds). */
  heartbeat_seconds: number;
  /** Max events per batch. */
  batch_max: number;
}

export interface TimelineEntry {
  started_at: string;
  ended_at: string;
  kind: "application" | "website";
  label: string; // app name or domain
  detail: string; // window/page title
  active_seconds: number;
}

export interface WorkSessionDTO {
  id: string;
  started_at: string;
  ended_at: string;
  active_seconds: number;
  apps: string[];
  domains: string[];
  inferred_customer?: string | null;
  inferred_campaign?: string | null;
  inferred_task?: string | null;
}

export interface AISummaryDTO {
  employee_id: string;
  date: string;
  summary: string;
  provider: string;
}

export interface AIInsightDTO {
  id: string;
  kind: string; // e.g. "context_switching", "manual_copy_paste"
  title: string;
  detail: string;
  recommendation: string;
  severity: "low" | "medium" | "high";
}
