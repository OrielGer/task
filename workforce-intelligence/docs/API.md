# API Reference

Base URL: `http://localhost:8000` (dev). Interactive OpenAPI docs: `/docs`.
All request/response bodies are JSON. All endpoints are versioned under
`/api/v1`.

## Authentication

Two principal types:

- **User** (dashboard/API): obtain a JWT from `POST /api/v1/auth/login`, then
  send `Authorization: Bearer <token>` on every request.
- **Device** (agent/extension): send `X-Device-Key` and `X-Device-Secret`
  headers (issued at enrollment). Identity is derived from the device.

RBAC roles: `SUPER_ADMIN`, `ORG_ADMIN`, `MANAGER`, `EMPLOYEE`. Tenant isolation
is enforced on every endpoint; cross-tenant ids return `404`.

Date query params (`start`, `end`, `date`) accept `YYYY-MM-DD` or ISO-8601.

---

## Auth
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/auth/login` | none | `{email, password}` → `{access_token, role, organization_id, user_id}` |
| GET | `/api/v1/auth/me` | user | Current principal + linked `employee_id` |
| GET | `/api/v1/auth/options` | none | `{demo_logins}`: true only when demo accounts are seeded (`SEED_DEMO`) |
| POST | `/api/v1/auth/change-password` | user | `{current_password, new_password}` (min 10 chars) → 204; wrong current → 400; audited |

## Administration / provisioning
| Method | Path | Roles | Body / notes |
|--------|------|-------|--------------|
| GET | `/api/v1/organizations` | user | `[{id, name}]`: every org for SUPER_ADMIN, otherwise only the caller's own |
| POST | `/api/v1/organizations` | SUPER_ADMIN | `{name, allowlisted_domains[]}` |
| POST | `/api/v1/organizations/{orgId}/users` | SUPER_ADMIN, ORG_ADMIN | `{email, full_name, password, role}` |
| POST | `/api/v1/organizations/{orgId}/employees` | SUPER_ADMIN, ORG_ADMIN | `{display_name, email, user_id?}` |
| POST | `/api/v1/organizations/{orgId}/teams` | SUPER_ADMIN, ORG_ADMIN | query: `name`, `manager_user_id?` |
| POST | `/api/v1/teams/{teamId}/members` | SUPER_ADMIN, ORG_ADMIN | query: `employee_id` |
| POST | `/api/v1/organizations/{orgId}/devices/enroll` | SUPER_ADMIN, ORG_ADMIN | `{employee_id, name}` → one-time `device_secret` |
| POST | `/api/v1/devices/{deviceId}/revoke` | SUPER_ADMIN, ORG_ADMIN | Disables the device credential |
| PUT | `/api/v1/organizations/{orgId}/allowlist` | SUPER_ADMIN, ORG_ADMIN | body: `["docs.google.com", ...]` |

## Agent / extension ingestion (device-authenticated; outbound-only)
| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/api/v1/agent/events/batch` | `{events: ActivityEvent[]}` | Activity focus intervals; dedup by `client_event_id` |
| POST | `/api/v1/agent/browser/batch` | `{events: BrowserEvent[]}` | Active-tab visits; URL sanitized |
| POST | `/api/v1/agent/content/batch` | `{events: ContentSnapshot[]}` | Allowlisted domains only; redacted; versioned |
| POST | `/api/v1/agent/heartbeat` | `{reported_at, agent_version, idle_seconds, is_locked}` | Updates presence |
| GET | `/api/v1/agent/config` | — | Non-executable config: allowlist + intervals (data only) |

All ingestion responses: `{accepted, duplicates, rejected}` (except heartbeat/config).

**ActivityEvent**: `{client_event_id, application, window_title, started_at,
ended_at, active_seconds, is_idle, is_locked}`
**BrowserEvent**: `{client_event_id, browser, domain, url, page_title,
started_at, ended_at, active_seconds, focused}`
**ContentSnapshot**: `{client_event_id, source, domain, url, content_type,
external_reference?, content, is_final, captured_at}`

## Employees (user-authenticated; role + tenant scoped, audited where noted)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/employees` | Visible employees for the caller's role |
| GET | `/api/v1/employees/{id}` | Single employee (role-visibility enforced) |
| GET | `/api/v1/employees/{id}/current` | Current activity (latest focus interval; `is_live` if within 5 min) |
| GET | `/api/v1/employees/{id}/timeline?start=&end=` | Merged app+website timeline |
| GET | `/api/v1/employees/{id}/applications?start=&end=` | Per-app usage |
| GET | `/api/v1/employees/{id}/websites?start=&end=` | Per-domain usage |
| GET | `/api/v1/employees/{id}/content` | Business content items (audited) |
| GET | `/api/v1/employees/{id}/content/{itemId}/versions` | Version history (audited) |
| GET | `/api/v1/employees/{id}/sessions?start=&end=` | Work sessions (rebuilt) |
| GET | `/api/v1/employees/{id}/insights?start=&end=` | Productivity recommendations |
| GET | `/api/v1/employees/{id}/summary?date=` | AI daily summary (audited) |

## Teams & analytics
| Method | Path | Roles | Notes |
|--------|------|-------|-------|
| GET | `/api/v1/teams/{id}/activity?start=&end=` | ORG_ADMIN, MANAGER(own), SUPER_ADMIN | Members + app/website usage |
| GET | `/api/v1/analytics/apps?start=&end=` | any (scope = visible employees) | Aggregate app usage |
| GET | `/api/v1/analytics/websites?start=&end=` | any | Aggregate website usage |
| GET | `/api/v1/analytics/workflows?start=&end=` | any | Repetitive-workflow detection (on the fly) |
| GET | `/api/v1/analytics/automation?start=&end=` | any | Automation opportunities; admins recompute+persist org-wide, others read scoped |

SUPER_ADMIN must pass `?organization_id=` to analytics endpoints; others are
pinned to their own org automatically.

## Integrations (marketing connectors)
| Method | Path | Roles | Notes |
|--------|------|-------|-------|
| GET | `/api/v1/integrations?organization_id=` | any | Status of each channel (meta/google/linkedin/crm/email) |
| PUT | `/api/v1/integrations/{orgId}/credentials` | SUPER_ADMIN, ORG_ADMIN | `{channel, display_name, token, config}` — token stored encrypted at rest |
| POST | `/api/v1/integrations/{orgId}/{channel}/sync` | SUPER_ADMIN, ORG_ADMIN | Pull campaigns (sandbox mode needs no credential) |
| GET | `/api/v1/integrations/{orgId}/campaigns?channel=` | any | Synced campaign mirror |

`INTEGRATION_MODE=sandbox` (default) returns deterministic sample data with no
network calls; `live` calls the real provider APIs with the decrypted token.

## Audit & jobs
| Method | Path | Roles | Notes |
|--------|------|-------|-------|
| GET | `/api/v1/audit?organization_id=&limit=&offset=` | SUPER_ADMIN, ORG_ADMIN | Paginated audit log (`{items,total,limit,offset}`) |
| POST | `/api/v1/jobs/{job}` | SUPER_ADMIN | Manually run a scheduled job: `retention` \| `summaries` \| `automation` |

Background jobs also run on a schedule when `SCHEDULER_ENABLED=true`.

## AI
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/ai/query` | `{question, employee_id?, team_id?}` → `{answer, provider, used_scope}` |

The AI query runs: authorization → query planner → tenant-scoped retrieval →
aggregation → provider. The LLM never has direct DB access. Scope is restricted
to the employees the caller may view; cross-tenant ids return `404`,
out-of-scope ids return `403`.

## Meta
| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | `{status, ai_provider}` |
| GET | `/` | Service banner |
