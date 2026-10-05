# Architecture — Workforce Intelligence Platform

> **What this is:** a transparent, consent-based workforce-analytics and
> marketing-productivity platform for **company-owned** Windows computers.
> It helps organizations understand how work gets done, surface inefficient
> workflows, and recommend automation — using **activity metadata** and
> **business content on explicitly allowlisted systems only**.
>
> **What this is not:** it is not spyware. It performs no raw keylogging, no
> password/credential/MFA/token capture, no screenshots, no webcam/mic
> capture, no stealth, no hidden processes, no remote command execution, and
> no monitoring outside approved work applications. See
> [`SECURITY.md`](./SECURITY.md) for the full list of prohibited behaviors
> and the threat model.

---

## 1. System overview

```
                        Company-owned Windows workstation
        ┌───────────────────────────────────────────────────────────┐
        │                                                             │
        │   ┌──────────────────────┐      ┌───────────────────────┐  │
        │   │  Windows Agent        │      │  Browser Extension    │  │
        │   │  (.NET 8, visible     │      │  (MV3, Chrome/Edge)   │  │
        │   │   installed app)      │      │                       │  │
        │   │                       │      │  - active tab only    │  │
        │   │  - active window/app  │      │  - sanitized URL      │  │
        │   │  - focus durations    │      │  - allowlisted-domain │  │
        │   │  - idle / lock state  │      │    content snapshots  │  │
        │   │  - heartbeat          │      │  - LOCAL redaction    │  │
        │   │  - SQLite buffer      │      │                       │  │
        │   └───────────┬──────────┘      └───────────┬───────────┘  │
        │               │  batched, redacted,         │              │
        │               │  outbound-only HTTPS        │              │
        └───────────────┼─────────────────────────────┼──────────────┘
                        │                             │
                        ▼                             ▼
            ┌───────────────────────────────────────────────┐
            │  Backend API (FastAPI, Python 3.12)            │
            │                                                │
            │  Ingestion  ─ device-authenticated batches     │
            │  AuthN/Z    ─ JWT users + device credentials   │
            │  RBAC       ─ SUPER_ADMIN/ORG_ADMIN/MANAGER/EMP│
            │  Tenancy    ─ organization_id on every query   │
            │  Redaction  ─ server-side defense-in-depth     │
            │  Sessions   ─ deterministic work-session engine│
            │  AI layer   ─ query-planner → provider adapter │
            │  Audit      ─ every content access logged      │
            │  Retention  ─ configurable cleanup jobs        │
            └───────┬───────────────────────┬────────────────┘
                    │                       │
          ┌─────────▼────────┐     ┌────────▼─────────┐     ┌───────────────┐
          │   PostgreSQL     │     │  Redis (optional)│     │  AI provider  │
          │  (system of      │     │  rate-limit /    │     │  (OpenAI /    │
          │   record)        │     │  cache / queue   │     │  Anthropic /  │
          └──────────────────┘     └──────────────────┘     │  Gemini /     │
                    ▲                                        │  Mock / local)│
                    │                                        └───────────────┘
            ┌───────┴────────────┐
            │  Web Dashboard      │
            │  (Next.js / React)  │
            │  org/employee/team  │
            │  analytics + AI chat│
            └─────────────────────┘
```

### Data-flow direction is one-way by design

Both collectors (agent and extension) **only send outbound telemetry**. The
backend never pushes commands, scripts, or executable payloads back to a
workstation. There is no control channel, no remote shell, no "executor."
The only backend→workstation responses are ordinary HTTP acknowledgements and
non-executable configuration (e.g. the current allowlist and debounce
interval), which the collectors treat as data, never as code.

---

## 2. Components

### 2.1 Windows Agent (`apps/windows-agent`, C# / .NET 8)
Collects **activity metadata** via standard, documented Windows APIs:

| Signal                | API                                             |
|-----------------------|-------------------------------------------------|
| Active window handle  | `GetForegroundWindow`                           |
| Active window title   | `GetWindowText`                                 |
| Owning process        | `GetWindowThreadProcessId` + `Process` name     |
| Idle time             | `GetLastInputInfo` (time since last input only) |
| Session lock/unlock   | `SystemEvents.SessionSwitch`                    |

It computes **focus intervals** (which app/window had focus and for how long),
an idle flag, and a periodic heartbeat. Events are buffered locally in SQLite
when the backend is unreachable, then **batched** to the API. It authenticates
with a **per-device credential** issued at enrollment; it cannot assert an
arbitrary `employee_id` (the server derives identity from the device).

**Explicitly out of scope for the agent:** reading process memory, capturing
typed characters, screenshots, injecting into other processes, elevating
silently, hiding itself, or executing anything received from the network.

### 2.2 Browser Extension (`apps/browser-extension`, TypeScript, MV3)
Tracks the **active tab only** (Chrome + Edge). Reports browser, sanitized
URL, page title, active start/end, active duration, and focus state, using the
browser `idle` and window-focus APIs so background tabs are not counted as
active work.

On **explicitly allowlisted business domains only**, it captures **business
text version snapshots** from recognized editors (`textarea`, approved text
inputs, `contenteditable`, supported rich-text editors) using **debounced
snapshots** and an immediate final snapshot on recognized Save/Publish/Send/
Submit actions. It **never** reads `input[type="password"]` or fields detected
to hold credentials/secrets/payment/MFA, and it applies **local secret
redaction and URL sanitization before anything leaves the machine.**

### 2.3 Backend API (`apps/api`, FastAPI / SQLAlchemy / Alembic)
See §3–§6. Responsibilities: authenticated ingestion, RBAC, tenant isolation,
server-side redaction (defense in depth), work-session construction, the AI
query pipeline, audit logging, retention jobs, and the analytics/query REST
surface.

### 2.4 Web Dashboard (`apps/dashboard`, Next.js / React / TypeScript)
Role-aware UI: organization overview, employee pages (timeline, apps,
websites, business content with version diffs, work sessions, AI summary and
recommendations), application/website analytics, and a chat-style AI manager.
Secrets are never rendered even if one were accidentally received.

### 2.5 Shared types (`packages/shared-types`, TypeScript)
Canonical event/content/DTO shapes shared by the extension and dashboard, kept
in sync with the backend Pydantic schemas.

---

## 3. Multi-tenancy & RBAC

The platform is SaaS-ready multi-tenant. **Every tenant-scoped table carries
`organization_id`**, and isolation is enforced at two layers:

1. **Application layer** — the authenticated principal carries an
   `organization_id`; request handlers receive a tenant-scoped DB session that
   injects `organization_id` filters, so a handler cannot "forget" to scope.
2. **Query layer** — repository/query helpers require an explicit
   `organization_id` argument; cross-tenant reads/writes are rejected.

Roles:

| Role          | Scope                                                        |
|---------------|--------------------------------------------------------------|
| `SUPER_ADMIN` | Platform administration across organizations.               |
| `ORG_ADMIN`   | Configure the org; view all employees within the org.       |
| `MANAGER`     | View only assigned teams.                                    |
| `EMPLOYEE`    | View their own analytics and recommendations only.          |

RBAC is enforced on **every** endpoint via dependency guards, combining role
checks with tenant scoping and, for manager/employee scopes, team/self
membership checks.

---

## 4. Data model (high level)

Core entities (all tenant-scoped except `organizations` itself):

```
organizations ──< users            (login principals; role + org)
              ──< employees         (monitored person; may link to a user)
              ──< teams ──< team_members >── employees
              ──< devices           (enrolled workstation; device credential)
              ──< activity_events   (app/window focus intervals, idle, lock)
              ──< browser_events    (active-tab visits, sanitized)
              ──< content_items ──< content_versions  (business text history)
              ──< work_sessions     (grouped activity → logical sessions)
              ──< ai_summaries
              ──< ai_insights
              ──< automation_opportunities
              ──< audit_logs        (who viewed what, when)
```

See [`docs/DATABASE.md`](./docs/DATABASE.md) for the column-level schema and
[`apps/api/alembic/versions`](./apps/api/alembic/versions) for migrations.

---

## 5. Work-session engine

A deterministic service groups ordered `activity_events` / `browser_events`
into logical **work sessions**:

- A session breaks when the idle gap between focus intervals exceeds a
  configurable threshold (default 5 min) or on day boundaries.
- Each session aggregates the apps/domains touched, active duration, and a
  best-effort inferred **customer / campaign / project / task** label using
  deterministic rules (domain → system, title keyword → entity).

The engine exposes a clean interface (`SessionClassifier`) so an AI-based
classifier can later replace or augment the deterministic rules **without**
changing callers.

---

## 6. AI layer

The LLM is **never** given direct database access. Every AI feature runs
through a constrained pipeline:

```
User question
  → Authorization check      (RBAC + tenant + subject scoping)
  → Query planner            (maps intent to a whitelist of safe queries)
  → Data retrieval           (tenant-scoped, parameterized)
  → Aggregation              (summarize/shape; strip anything sensitive)
  → AI provider (adapter)    (prompt + aggregated context only)
  → Answer
```

Logical services: `WorkUnderstandingService`, `ProductivityAnalysisService`,
`ContentAnalysisService`, `WorkflowAnalysisService`,
`AutomationRecommendationService`, `ManagerAssistantService`.

**Provider abstraction** (`AIProvider`) supports OpenAI, Anthropic, Gemini,
and a built-in **Mock** provider used automatically when no API key is
configured, so the full MVP runs offline. The provider is selected by
configuration — no provider is hard-coded through the codebase.

Recommendations are **workflow- and outcome-based** (context switching,
repetitive copy/paste, long rework cycles, automatable sequences), explicitly
avoiding naive surveillance metrics such as keystroke counts.

---

## 7. Marketing-focused analysis

First-class concepts: Customer, Campaign, Channel, Creative, Headline, CTA,
Email, CRM activity, Ad copy, AI prompt, Final output. Integration interfaces
(`MarketingIntegration`) are defined for Meta Ads, Google Ads, LinkedIn Ads,
HubSpot, and Gmail/Outlook; the first milestone ships the interfaces and the
deterministic analysis, not every live integration.

## 8. Repetitive-workflow detection

Detects repeated event sequences (e.g. *CRM → copy details → Ads Manager →
paste → configure → publish*) and stores: workflow name, occurrences, average
duration, employees involved, estimated weekly time, and an automation score,
with an estimated potential time saving.

---

## 9. Deployment

Development runs on **Docker Compose**: Postgres, Redis, API, and dashboard.
TLS termination is expected at a reverse proxy / load balancer in production
(the app emits secure headers and is TLS-ready). Collectors talk to the API
over HTTPS only.

## 10. Key engineering decisions

- **Outbound-only collectors / no control channel** — the single most
  important design choice; it is what keeps this an analytics product and not
  a remote-administration tool.
- **Redact at the edge, re-redact at the server** — redaction runs on the
  workstation before upload *and* again on ingestion, so a buggy or outdated
  collector cannot defeat the privacy guarantee.
- **Device-derived identity** — the agent cannot spoof another employee.
- **Deterministic first, AI second** — sessions/workflows work without any AI
  key; AI augments but is never on the trust path for authorization or tenancy.
- **Allowlist-gated content** — business-text capture is off by default and
  only runs on domains an org admin explicitly approves.
