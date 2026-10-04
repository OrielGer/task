// TypeScript interfaces mirroring the backend API response shapes.
// See apps/api/app/schemas.py for the authoritative definitions.

export type Role = "ORG_ADMIN" | "MANAGER" | "EMPLOYEE" | string;

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
