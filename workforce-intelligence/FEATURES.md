# Implemented Features & Next Milestones

## Deliverables map (per the brief)

| # | Deliverable | Where |
|---|-------------|-------|
| 1 | Working repository | this monorepo |
| 2 | Docker development environment | `docker-compose.yml` (Postgres + Redis + API + dashboard) |
| 3 | Setup instructions | `README.md` |
| 4 | Agent installation instructions | `apps/windows-agent/README.md` |
| 5 | Extension loading instructions | `apps/browser-extension/README.md` |
| 6 | Architecture documentation | `ARCHITECTURE.md` |
| 7 | Database diagram/documentation | `docs/DATABASE.md` |
| 8 | API documentation | `docs/API.md` (+ live OpenAPI at `/docs`) |
| 9 | Threat model | `SECURITY.md` §9 |
| 10 | Implemented features | this file |
| 11 | Next recommended milestones | this file + `IMPLEMENTATION_PLAN.md` |

## Milestone 1 — implemented (verified)

Every item of the required MVP vertical slice works end-to-end:

1. ✅ Create organization — `POST /api/v1/organizations` (SUPER_ADMIN).
2. ✅ Create manager — `POST /api/v1/organizations/{id}/users` (role MANAGER).
3. ✅ Create employee — `POST /api/v1/organizations/{id}/employees`.
4. ✅ Register Windows device — `POST /api/v1/organizations/{id}/devices/enroll`
   (returns a one-time device secret; identity is server-derived).
5. ✅ Windows agent reports active application/window — `apps/windows-agent`
   (metadata only) → `POST /api/v1/agent/events/batch`.
6. ✅ Browser extension reports active URL/title — `apps/browser-extension`
   → `POST /api/v1/agent/browser/batch` (active tab only; URL sanitized).
7. ✅ Approved business domain captures text snapshots — allowlist-gated,
   debounced, redacted → `POST /api/v1/agent/content/batch`, versioned.
8. ✅ Events appear in backend — ingestion with dedup + redaction.
9. ✅ Employee timeline renders in dashboard — `/employees/[id]`.
10. ✅ Manager can see application/website usage — `/analytics`, team activity.
11. ✅ AI generates daily employee summary — mock provider by default,
    `GET /api/v1/employees/{id}/summary`.
12. ✅ AI generates 1–5 workflow recommendations — productivity insights
    (`/insights`) + repetitive-workflow/automation detection (`/analytics/workflows`).

### Cross-cutting, also implemented
- Multi-tenancy (`organization_id` everywhere) + two-layer isolation.
- RBAC (SUPER_ADMIN / ORG_ADMIN / MANAGER / EMPLOYEE) on every endpoint.
- JWT user auth + per-device credentials + device revocation.
- `SecretRedactor` + URL sanitizer (edge + server) — the "never capture
  passwords/secrets" guarantee, unit-tested on both Python and TypeScript sides.
- Deterministic work-session engine (pluggable `SessionClassifier`).
- AI provider abstraction (mock / OpenAI / Anthropic / Gemini) + constrained
  query pipeline (no direct DB access for the LLM).
- Repetitive-workflow detection + automation scoring + potential-savings.
- Audit logging on content access; configurable retention + cleanup job.
- Marketing-integration interfaces (Meta/Google/LinkedIn/HubSpot/Email) defined.
- Security hardening: secure headers, rate limiting, parameterized queries,
  input validation, TLS-ready.
- Tests: 50 backend tests + 9 extension redaction tests, all passing.

## Milestone 2 — implemented (verified)

- **Marketing integrations** behind `MarketingIntegration`: HubSpot, Meta Ads,
  and LinkedIn Ads live `httpx` connectors (Google Ads / Email documented
  stubs), a **sandbox mode** (default, fully offline) for demos/tests, per-org
  credentials **encrypted at rest** (Fernet), a synced `campaigns` mirror, and
  configure/sync/read endpoints.
- **AI session classification** (`AISessionClassifier`) behind the existing
  `SessionClassifier`, opt-in via `AI_SESSION_CLASSIFIER`, with a safe
  deterministic fallback when the provider is mock or returns unparseable
  output.
- **Background scheduler** (APScheduler): retention cleanup, nightly AI
  summaries, and automation recompute, wired into the app lifespan
  (`SCHEDULER_ENABLED`), plus a SUPER_ADMIN manual trigger endpoint.
- **Persisted automation opportunities** + `GET /analytics/automation`.
- **Paginated audit endpoint** (`GET /audit`) and list pagination.
- **Redis-backed rate limiter** with in-memory fail-open fallback.
- **CI** (GitHub Actions): backend pytest + lint, extension build/typecheck/
  tests, dashboard typecheck/build.
- **Dashboard**: admin provisioning UI, integrations config, audit viewer, and
  automation view (see `apps/dashboard`).

Backend test count: **69 passing**.

## Still deferred (clearly stubbed, not hidden)
- Google Ads / Email **live** connectors (sandbox works; live raises a clear,
  dated `IntegrationError`) — need developer tokens / OAuth app setup.
- SSO (SAML/OIDC), signed MSI installer, data-subject export/delete tooling,
  distributed tracing/metrics — Milestone 3.

## Next recommended milestones

**Milestone 2 — deepen**
- Implement the marketing connectors behind `MarketingIntegration` (OAuth +
  per-org credentials), starting with HubSpot + Meta Ads.
- Swap/augment the deterministic `SessionClassifier` with an AI classifier.
- Scheduler (APScheduler/Celery) for retention cleanup and nightly AI summaries.
- Richer workflow-sequence mining (approximate/near-duplicate sequences).
- Redis rate limiting + ingestion queue; pagination on all list endpoints.

**Milestone 3 — hardening & scale**
- Signed MSI installer + auto-update for the agent; MDM deployment guide.
- SSO (SAML/OIDC) for the dashboard; per-org data residency.
- Observability (metrics/tracing), alerting, SLOs.
- Data-subject tooling (export/delete) and a consent-management UI.
- Formal pen-test against the threat model in `SECURITY.md`.
