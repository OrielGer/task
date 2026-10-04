// TypeScript interfaces mirroring the backend API response shapes.
// See apps/api/app/schemas.py for the authoritative definitions.

export type Role = "SUPER_ADMIN" | "ORG_ADMIN" | "MANAGER" | "EMPLOYEE" | string;

/** Roles that can be assigned when provisioning a user within an organization. */
export type ProvisionableRole = "ORG_ADMIN" | "MANAGER" | "EMPLOYEE";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: Role;
  organization_id: string | null;
  user_id: string;
}

export interface Me {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  organization_id: string | null;
  employee_id: string | null;
}

export type EmployeeStatus = "active" | "idle" | "offline" | string;

export interface Employee {
  id: string;
  display_name: string;
  email: string;
  status: EmployeeStatus;
  last_seen_at: string | null;
}

export interface CurrentActivity {
  status: EmployeeStatus;
  kind: "application" | "website" | null;
  label: string | null;
  detail: string | null;
  since: string | null;
  last_seen_at: string | null;
  is_live: boolean;
}

export type TimelineKind = "application" | "website" | string;

export interface TimelineEntry {
  started_at: string;
  ended_at: string;
  kind: TimelineKind;
  label: string;
  detail: string;
  active_seconds: number;
}

export interface UsageRow {
  label: string;
  active_seconds: number;
  event_count: number;
}

export interface WorkSession {
  id: string;
  started_at: string;
  ended_at: string;
  active_seconds: number;
  /** comma-separated application names */
  apps: string;
  /** comma-separated domains */
  domains: string;
  inferred_customer: string | null;
  inferred_campaign: string | null;
  inferred_task: string | null;
}

export interface ContentItem {
  id: string;
  source: string;
  domain: string;
  url: string;
  content_type: string;
  external_reference: string | null;
  updated_at: string;
}

export interface ContentVersion {
  id: string;
  version_number: number;
  /** already redacted server-side */
  content: string;
  is_final: boolean;
  created_at: string;
}

export interface AISummary {
  employee_id: string;
  date: string;
  summary: string;
  provider: string;
}

export type InsightSeverity = "low" | "medium" | "high" | "critical" | string;

export interface AIInsight {
  id: string;
  kind: string;
  title: string;
  detail: string;
  recommendation: string;
  severity: InsightSeverity;
}

export interface WorkflowRow {
  workflow_name: string;
  occurrences_per_week: number;
  average_seconds: number;
  employees: string[];
  estimated_weekly_seconds: number;
  /** 0..1 */
  automation_score: number;
  potential_weekly_savings_seconds: number;
}

export interface AIQueryRequest {
  question: string;
  employee_id?: string | null;
  team_id?: string | null;
}

export interface AIQueryResponse {
  answer: string;
  provider: string;
  used_scope: string;
}

/** Optional ISO date range (YYYY-MM-DD or ISO datetime). */
export interface DateRange {
  start?: string;
  end?: string;
}

// ── Admin / provisioning ─────────────────────────────────────────────────────

export interface OrganizationCreateRequest {
  name: string;
  allowlisted_domains: string[];
}

export interface OrganizationSummary {
  id: string;
  name: string;
}

export interface UserCreateRequest {
  email: string;
  full_name: string;
  password: string;
  role: ProvisionableRole;
}

export interface UserSummary {
  id: string;
  email: string;
  role: Role;
}

export interface EmployeeCreateRequest {
  display_name: string;
  email: string;
  user_id?: string;
}

export interface Team {
  id: string;
  name: string;
  manager_user_id: string | null;
}

export interface TeamMember {
  id: string;
  team_id: string;
  employee_id: string;
}

export interface DeviceEnrollRequest {
  employee_id: string;
  name: string;
}

/** Returned once on enrollment. `device_secret` is not retrievable again. */
export interface DeviceEnrollment {
  device_id: string;
  device_key: string;
  device_secret: string;
  note: string;
}

export interface DeviceRevokeResult {
  id: string;
  is_active: boolean;
}

export interface AllowlistResult {
  organization_id: string;
  allowlisted_domains: string[];
}

// ── Integrations ─────────────────────────────────────────────────────────────

export type IntegrationChannel =
  | "meta"
  | "google"
  | "linkedin"
  | "crm"
  | "email"
  | string;

export interface IntegrationStatus {
  channel: IntegrationChannel;
  display_name: string;
  configured: boolean;
  is_active: boolean;
  last_synced_at: string | null;
}

export interface IntegrationCredentialRequest {
  channel: IntegrationChannel;
  display_name: string;
  /** Secret — never rendered back by the UI. */
  token: string;
  config: Record<string, unknown>;
}

/** Status payload returned when a credential is saved. */
export interface IntegrationCredentialResult {
  channel: IntegrationChannel;
  display_name?: string;
  configured?: boolean;
  is_active?: boolean;
}

export interface IntegrationSyncResult {
  channel: IntegrationChannel;
  synced: number;
}

export type CampaignStatus = "active" | "paused" | "ended" | string;

export interface Campaign {
  id: string;
  channel: IntegrationChannel;
  external_id: string;
  name: string;
  status: CampaignStatus;
  synced_at: string | null;
}

// ── Analytics automation + audit ─────────────────────────────────────────────

export interface AutomationOpportunity {
  id: string;
  workflow_name: string;
  occurrences_per_week: number;
  average_seconds: number;
  employees: string[];
  estimated_weekly_seconds: number;
  /** 0..1 */
  automation_score: number;
  potential_weekly_savings_seconds: number;
}

export interface AuditLogEntry {
  id: string;
  viewer_user_id: string;
  employee_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  created_at: string;
}

export interface AuditPage {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}
