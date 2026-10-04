# Security & Privacy

This platform monitors **company-owned** computers for **work analytics**, and
employees are **informed** that these devices are monitored. Privacy is a
product requirement, not an afterthought. This document defines the hard
boundaries, the controls, and the threat model.

---

## 1. Prohibited behaviors (hard requirements)

The following are **never** implemented anywhere in this codebase. They are
rejected in code review and covered by tests where testable:

- ❌ Raw system-wide keylogging / capturing typed characters
- ❌ Password capture (`input[type="password"]` is never read)
- ❌ MFA / OTP / one-time-code capture
- ❌ API-key, access-token, refresh-token, JWT, or `Authorization`-header capture
- ❌ Clipboard password/secret capture
- ❌ Screenshots, screen scraping of arbitrary windows
- ❌ Webcam or microphone recording
- ❌ Stealth operation / hidden processes / hidden installation
- ❌ Disabling, bypassing, or evading security software / antivirus
- ❌ Persistence techniques intended to resist removal
- ❌ Monitoring outside approved work applications
- ❌ Reading other processes' memory or injecting into them
- ❌ **Remote command execution / any backend→workstation control channel**

The monitoring agent **must be visible** in the OS "installed applications"
list and clearly identifiable as company monitoring software. Uninstalling it
uses the ordinary OS uninstall flow.

## 2. What is collected

**Windows agent (metadata only):** employee/device identity, active process
name, active application, active window title, focus start/end, active
duration, idle state, workstation locked/unlocked, heartbeat.

**Browser extension (active tab only):** browser, domain, **sanitized** URL,
page title, active start/end, active duration, focus state.

**Business content (allowlisted domains only):** debounced text snapshots from
approved editors, with version history — **after local redaction**.

Nothing else. Background tabs are not counted as active work. Non-allowlisted
domains produce visit metadata only (sanitized URL + title + duration), never
content.

## 3. Secret redaction (defense in depth)

A configurable `SecretRedactor` runs **on the workstation before any content
leaves the machine**, and again **on the server at ingestion**. It blocks /
masks:

- password fields and values
- OTP / MFA codes
- access tokens, refresh tokens, JWTs (when detectable)
- API keys and generic high-entropy secrets
- `Authorization` headers (`Authorization: Bearer …` → `Authorization: [REDACTED]`)
- private keys (PEM blocks)
- credit-card numbers (where detectable, Luhn-checked)

**URL sanitization** strips sensitive query parameters:
`token, access_token, refresh_token, secret, password, auth, authorization,
code, api_key, key` (and their common variants), replacing values with
`[REDACTED]`.

The redactor is shared logic: the TypeScript port in the extension and the
Python implementation in the backend are kept behaviorally aligned and both are
unit-tested, including the explicit guarantee that **password fields are never
captured** and **secrets are redacted before upload**.

## 4. AuthN / AuthZ

- **Users** authenticate with email + password (hashed with a strong KDF via
  passlib — pbkdf2-sha256 by default; bcrypt/argon2 configurable) and receive
  short-lived JWT access tokens.
- **RBAC** (`SUPER_ADMIN`, `ORG_ADMIN`, `MANAGER`, `EMPLOYEE`) is enforced on
  every endpoint via dependency guards.
- **Tenant isolation**: every tenant-scoped query is filtered by
  `organization_id`; a principal from organization A can never read or write
  organization B's data. This is covered by tests.
- **Devices** authenticate with a **per-device credential** issued at
  enrollment. The server derives `employee_id`/`organization_id` from the
  device record, so an agent **cannot impersonate another employee** by
  supplying a different id. Optional HMAC request signing is supported for
  agent batches. Devices can be **revoked**, immediately rejecting their
  credential.

## 5. Platform hardening

- Input validation via Pydantic on every request body.
- SQL-injection protection via SQLAlchemy parameterized queries / ORM (no
  string-built SQL).
- Secure HTTP headers (HSTS-ready, `X-Content-Type-Options`, `X-Frame-Options`,
  referrer policy, CSP for the dashboard).
- Rate limiting on auth and ingestion endpoints (Redis-backed when configured,
  with an in-memory fail-open fallback).
- Audit logging of every access to detailed employee content.
- Marketing-integration tokens are **encrypted at rest** (Fernet; key from
  `INTEGRATION_ENC_KEY`) and never returned by the API.
- TLS-ready deployment (TLS terminated at the proxy; collectors use HTTPS).

## 6. Audit logging

Every access to detailed employee content writes an `audit_logs` row:
`viewer_user_id, organization_id, employee_id, action, resource_type,
resource_id, timestamp`. Example: *ORG_ADMIN viewed employee content history.*

## 7. Retention

Configurable, with cleanup jobs. Suggested defaults:

| Data                  | Default retention |
|-----------------------|-------------------|
| Activity events       | 180 days          |
| Draft content versions| 90 days           |
| AI summaries          | 12 months         |
| Aggregated analytics  | 24 months         |

## 8. The AI trust boundary

The LLM never touches the database directly. All AI features go through
`question → authz → query planner → retrieval → aggregation → AI → answer`.
The model receives only aggregated, tenant-scoped, redacted context. Prompt
inputs are treated as data; model output is never executed.

---

## 9. Threat model

Notation: **Asset** → **Threat** → **Mitigation**.

### T1 — A rogue/compromised agent impersonates another employee
- **Threat:** an attacker with one device's software asserts another
  `employee_id` to read or pollute someone else's data.
- **Mitigation:** identity is derived server-side from the device credential,
  not from the payload. Ingestion ignores any client-supplied employee/org id
  that conflicts with the device record. Devices are revocable.

### T2 — Cross-tenant data access (org A reads org B)
- **Threat:** a manager/admin or a bug reads another organization's data.
- **Mitigation:** two-layer tenancy (scoped session + explicit
  `organization_id` on queries); RBAC guards; dedicated tenant-isolation tests.

### T3 — Over-privileged role views
- **Threat:** a MANAGER views employees outside their teams; an EMPLOYEE views
  others.
- **Mitigation:** role guards combine with team-membership / self checks on
  every employee/team endpoint.

### T4 — Secrets captured in business content
- **Threat:** a password/token/card number is typed into an allowlisted editor
  and captured.
- **Mitigation:** password fields are never read; edge redaction + server
  redaction; URL sanitization; allowlist-only content capture; content
  rendering in the dashboard re-checks and never shows secrets.

### T5 — Scope creep into surveillance
- **Threat:** the collector is quietly extended to keylogging, screenshots,
  memory reads, or non-work apps.
- **Mitigation:** hard prohibitions in this doc and `CLAUDE.md`; code structure
  provides no primitive for it; agent is visible and uninstallable; content
  capture is allowlist-gated and off by default.

### T6 — The platform becomes a remote-administration tool
- **Threat:** a backend→workstation command/control path is added (the most
  dangerous failure mode).
- **Mitigation:** collectors are **outbound-only**. There is no command
  endpoint, no executor, no remote shell. Backend responses are acknowledgements
  and non-executable config only, consumed as data. This invariant is called
  out in `CLAUDE.md` and `ARCHITECTURE.md` and must be preserved in review.

### T7 — Stolen device credential
- **Threat:** a device token is exfiltrated and used elsewhere.
- **Mitigation:** per-device credentials, revocation, optional HMAC signing,
  TLS, rate limiting; a revoked/!active device is rejected.

### T8 — Prompt injection via captured content into the AI layer
- **Threat:** captured text contains instructions aiming to exfiltrate data or
  cross tenants through the AI.
- **Mitigation:** the AI has no DB access and no tools; retrieval is
  tenant-scoped and authorization-gated *before* the model runs; model output
  is treated as text and never executed or used to authorize anything.

### T9 — PII exposure through logs/analytics
- **Threat:** sensitive content leaks into logs or aggregate views.
- **Mitigation:** redaction before storage; audit logging of content access;
  retention limits; dashboards show diffs/versions but never secret-flagged
  content.

---

## 10. Responsible-use expectations

Deploy only on **company-owned** devices, with **employee notification** and in
compliance with applicable law (e.g. GDPR and local labor law). Configure the
allowlist to approved business systems only. Keep the agent visible. Use audit
logs and retention. This platform is built to make *informed, proportionate,
work-focused* analytics possible — and to make covert surveillance structurally
difficult.
