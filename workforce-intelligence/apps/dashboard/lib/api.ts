// Typed fetch client + auth token handling.
//
// This is a read/analytics UI. All business content returned by the API is
// already redacted server-side; the client only renders it.

import type {
  AIInsight,
  AIQueryRequest,
  AIQueryResponse,
  AISummary,
  AllowlistResult,
  AuditPage,
  AuthOptions,
  AutomationOpportunity,
  ChangePasswordRequest,
  Campaign,
  ContentItem,
  CurrentActivity,
  ContentVersion,
  DateRange,
  DeviceEnrollment,
  DeviceEnrollRequest,
  DeviceRevokeResult,
  Employee,
  EmployeeCreateRequest,
  IntegrationChannel,
  IntegrationCredentialRequest,
  IntegrationCredentialResult,
  IntegrationStatus,
  IntegrationSyncResult,
  LoginRequest,
  Me,
  OrganizationCreateRequest,
  OrganizationSummary,
  Team,
  TeamMember,
  TokenResponse,
  TimelineEntry,
  UsageRow,
  UserCreateRequest,
  UserSummary,
  WorkflowRow,
  WorkSession,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "wfi_token";

/** Emitted (client-side) whenever the API returns 401 so the auth layer can
 * clear state and redirect to /login. */
export const UNAUTHORIZED_EVENT = "wfi:unauthorized";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// ── Token storage (client-side only) ────────────────────────────────────────
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage unavailable — ignore */
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

// ── Active organization (SUPER_ADMIN only) ───────────────────────────────────
// A super admin has no organization of their own; org-scoped endpoints need an
// explicit ?organization_id=. The auth layer sets this for super admins only, and
// request() then adds it to every authenticated call that doesn't name an org.
const ACTIVE_ORG_KEY = "wfi_active_org";
let activeOrganizationId: string | null = null;

export function getStoredActiveOrganization(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACTIVE_ORG_KEY);
  } catch {
    return null;
  }
}

export function setActiveOrganization(id: string | null): void {
  activeOrganizationId = id;
  if (typeof window === "undefined") return;
  try {
    if (id) window.localStorage.setItem(ACTIVE_ORG_KEY, id);
    else window.localStorage.removeItem(ACTIVE_ORG_KEY);
  } catch {
    /* storage unavailable — ignore */
  }
}

/** Stop adding the org to requests (sign-out / non-super user) but keep the
 * stored choice, so a super admin's next session resumes on the same org. */
export function forgetActiveOrganization(): void {
  activeOrganizationId = null;
}

function withActiveOrganization(path: string): string {
  if (!activeOrganizationId || /[?&]organization_id=/.test(path)) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}organization_id=${encodeURIComponent(activeOrganizationId)}`;
}

// ── Core request helper ──────────────────────────────────────────────────────
interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Skip attaching the Authorization header (used by login). */
  anonymous?: boolean;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  if (!opts.anonymous) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    path = withActiveOrganization(path);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(0, `Network error reaching API: ${String(err)}`);
  }

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    let body: unknown = undefined;
    let detail = res.statusText;
    try {
      body = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail?: unknown }).detail;
        if (typeof d === "string") detail = d;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`, body);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ── Query string helper ──────────────────────────────────────────────────────
function qs(params: Readonly<Record<string, string | undefined>>): string {
  const entries = Object.entries(params).filter(
    (e): e is [string, string] => typeof e[1] === "string" && e[1] !== ""
  );
  if (entries.length === 0) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of entries) sp.set(k, v);
  return `?${sp.toString()}`;
}

// ── Public API surface ────────────────────────────────────────────────────────
export const api = {
  login(body: LoginRequest): Promise<TokenResponse> {
    return request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body,
      anonymous: true,
    });
  },

  me(signal?: AbortSignal): Promise<Me> {
    return request<Me>("/api/v1/auth/me", { signal });
  },

  authOptions(signal?: AbortSignal): Promise<AuthOptions> {
    return request<AuthOptions>("/api/v1/auth/options", { anonymous: true, signal });
  },

  changePassword(body: ChangePasswordRequest): Promise<void> {
    return request<void>("/api/v1/auth/change-password", { method: "POST", body });
  },

  /** SUPER_ADMIN: every organization. Other roles: only their own. */
  organizations(signal?: AbortSignal): Promise<OrganizationSummary[]> {
    return request<OrganizationSummary[]>("/api/v1/organizations", { signal });
  },

  employees(signal?: AbortSignal): Promise<Employee[]> {
    return request<Employee[]>("/api/v1/employees", { signal });
  },

  employee(id: string, signal?: AbortSignal): Promise<Employee> {
    return request<Employee>(`/api/v1/employees/${encodeURIComponent(id)}`, { signal });
  },

  currentActivity(id: string, signal?: AbortSignal): Promise<CurrentActivity> {
    return request<CurrentActivity>(
      `/api/v1/employees/${encodeURIComponent(id)}/current`,
      { signal }
    );
  },

  timeline(id: string, range: DateRange = {}, signal?: AbortSignal): Promise<TimelineEntry[]> {
    return request<TimelineEntry[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/timeline${qs({ ...range })}`,
      { signal }
    );
  },

  applications(id: string, range: DateRange = {}, signal?: AbortSignal): Promise<UsageRow[]> {
    return request<UsageRow[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/applications${qs({ ...range })}`,
      { signal }
    );
  },

  websites(id: string, range: DateRange = {}, signal?: AbortSignal): Promise<UsageRow[]> {
    return request<UsageRow[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/websites${qs({ ...range })}`,
      { signal }
    );
  },

  content(id: string, signal?: AbortSignal): Promise<ContentItem[]> {
    return request<ContentItem[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/content`,
      { signal }
    );
  },

  contentVersions(id: string, itemId: string, signal?: AbortSignal): Promise<ContentVersion[]> {
    return request<ContentVersion[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/content/${encodeURIComponent(itemId)}/versions`,
      { signal }
    );
  },

  sessions(id: string, range: DateRange = {}, signal?: AbortSignal): Promise<WorkSession[]> {
    return request<WorkSession[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/sessions${qs({ ...range })}`,
      { signal }
    );
  },

  insights(id: string, range: DateRange = {}, signal?: AbortSignal): Promise<AIInsight[]> {
    return request<AIInsight[]>(
      `/api/v1/employees/${encodeURIComponent(id)}/insights${qs({ ...range })}`,
      { signal }
    );
  },

  summary(id: string, date?: string, signal?: AbortSignal): Promise<AISummary> {
    return request<AISummary>(
      `/api/v1/employees/${encodeURIComponent(id)}/summary${qs({ date })}`,
      { signal }
    );
  },

  analyticsApps(range: DateRange = {}, signal?: AbortSignal): Promise<UsageRow[]> {
    return request<UsageRow[]>(`/api/v1/analytics/apps${qs({ ...range })}`, { signal });
  },

  analyticsWebsites(range: DateRange = {}, signal?: AbortSignal): Promise<UsageRow[]> {
    return request<UsageRow[]>(`/api/v1/analytics/websites${qs({ ...range })}`, { signal });
  },

  analyticsWorkflows(range: DateRange = {}, signal?: AbortSignal): Promise<WorkflowRow[]> {
    return request<WorkflowRow[]>(`/api/v1/analytics/workflows${qs({ ...range })}`, { signal });
  },

  aiQuery(body: AIQueryRequest, signal?: AbortSignal): Promise<AIQueryResponse> {
    return request<AIQueryResponse>("/api/v1/ai/query", {
      method: "POST",
      body,
      signal,
    });
  },

  analyticsAutomation(
    range: DateRange = {},
    signal?: AbortSignal
  ): Promise<AutomationOpportunity[]> {
    return request<AutomationOpportunity[]>(
      `/api/v1/analytics/automation${qs({ ...range })}`,
      { signal }
    );
  },

  // ── Admin / provisioning ─────────────────────────────────────────────────
  // SUPER_ADMIN only.
  createOrganization(body: OrganizationCreateRequest): Promise<OrganizationSummary> {
    return request<OrganizationSummary>("/api/v1/organizations", {
      method: "POST",
      body,
    });
  },

  createUser(orgId: string, body: UserCreateRequest): Promise<UserSummary> {
    return request<UserSummary>(
      `/api/v1/organizations/${encodeURIComponent(orgId)}/users`,
      { method: "POST", body }
    );
  },

  createEmployee(orgId: string, body: EmployeeCreateRequest): Promise<Employee> {
    return request<Employee>(
      `/api/v1/organizations/${encodeURIComponent(orgId)}/employees`,
      { method: "POST", body }
    );
  },

  createTeam(orgId: string, name: string, managerUserId?: string): Promise<Team> {
    return request<Team>(
      `/api/v1/organizations/${encodeURIComponent(orgId)}/teams${qs({
        name,
        manager_user_id: managerUserId,
      })}`,
      { method: "POST" }
    );
  },

  addTeamMember(teamId: string, employeeId: string): Promise<TeamMember> {
    return request<TeamMember>(
      `/api/v1/teams/${encodeURIComponent(teamId)}/members${qs({
        employee_id: employeeId,
      })}`,
      { method: "POST" }
    );
  },

  enrollDevice(orgId: string, body: DeviceEnrollRequest): Promise<DeviceEnrollment> {
    return request<DeviceEnrollment>(
      `/api/v1/organizations/${encodeURIComponent(orgId)}/devices/enroll`,
      { method: "POST", body }
    );
  },

  revokeDevice(deviceId: string): Promise<DeviceRevokeResult> {
    return request<DeviceRevokeResult>(
      `/api/v1/devices/${encodeURIComponent(deviceId)}/revoke`,
      { method: "POST" }
    );
  },

  setAllowlist(orgId: string, domains: string[]): Promise<AllowlistResult> {
    return request<AllowlistResult>(
      `/api/v1/organizations/${encodeURIComponent(orgId)}/allowlist`,
      { method: "PUT", body: domains }
    );
  },

  // ── Integrations ─────────────────────────────────────────────────────────
  // SUPER_ADMIN passes organizationId; org-scoped roles omit it.
  integrations(
    organizationId?: string,
    signal?: AbortSignal
  ): Promise<IntegrationStatus[]> {
    return request<IntegrationStatus[]>(
      `/api/v1/integrations${qs({ organization_id: organizationId })}`,
      { signal }
    );
  },

  setIntegrationCredential(
    orgId: string,
    body: IntegrationCredentialRequest
  ): Promise<IntegrationCredentialResult> {
    return request<IntegrationCredentialResult>(
      `/api/v1/integrations/${encodeURIComponent(orgId)}/credentials`,
      { method: "PUT", body }
    );
  },

  syncIntegration(
    orgId: string,
    channel: IntegrationChannel
  ): Promise<IntegrationSyncResult> {
    return request<IntegrationSyncResult>(
      `/api/v1/integrations/${encodeURIComponent(orgId)}/${encodeURIComponent(
        channel
      )}/sync`,
      { method: "POST" }
    );
  },

  campaigns(
    orgId: string,
    channel?: IntegrationChannel,
    signal?: AbortSignal
  ): Promise<Campaign[]> {
    return request<Campaign[]>(
      `/api/v1/integrations/${encodeURIComponent(orgId)}/campaigns${qs({
        channel,
      })}`,
      { signal }
    );
  },

  // ── Audit ──────────────────────────────────────────────────────────────────
  audit(
    params: { organizationId?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal
  ): Promise<AuditPage> {
    return request<AuditPage>(
      `/api/v1/audit${qs({
        organization_id: params.organizationId,
        limit: params.limit !== undefined ? String(params.limit) : undefined,
        offset: params.offset !== undefined ? String(params.offset) : undefined,
      })}`,
      { signal }
    );
  },
};
