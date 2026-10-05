# Implementation Plan

Build a working **vertical slice** first (Milestone 1), then broaden. After
each major step: build, run tests, fix, update docs, reach a commit-ready
state.

## Milestone 1 — vertical slice (this deliverable)

Goal: org → manager → employee → device → agent event → browser event →
allowlisted content snapshot → backend → dashboard timeline → manager
app/website usage → AI daily summary → AI workflow recommendations.

1. ✅ Architecture, security, threat model, guardrails docs.
2. Monorepo skeleton, Docker Compose, `.env.example`, shared types.
3. Backend: config, DB, models, Alembic migration, JWT auth, password hashing,
   RBAC, two-layer tenant isolation, device credentials, audit logging.
4. Redaction (`SecretRedactor` + URL sanitizer) and ingestion endpoints
   (`/agent/events/batch`, `/agent/content/batch`, `/agent/heartbeat`) with
   device auth and content-version dedup/debounce storage.
5. Work-session engine (deterministic) + AI provider abstraction (Mock default)
   + AI services + `/ai/query` query-planner pipeline + analytics/employee/team
   endpoints.
6. Browser extension (MV3): active-tab tracking, idle/focus, allowlist content
   snapshots, local redaction + URL sanitization.
7. Windows agent (.NET 8): active window/app, idle, lock, heartbeat, SQLite
   buffer, batched upload, device credential — metadata only, no control path.
8. Dashboard (Next.js): login, org overview, employee page, analytics, AI chat.
9. Tests: redaction, URL sanitization, RBAC, tenant isolation, ingestion,
   content versions, device anti-impersonation.
10. Seed/demo data, run tests, verify Docker Compose, finalize README + API +
    DB docs, commit & push.

## Milestone 2 — deepen

- Live marketing integrations (Meta/Google/LinkedIn Ads, HubSpot, Gmail/Outlook)
  behind the `MarketingIntegration` interface.
- AI-based work-session classification behind the existing `SessionClassifier`.
- Richer workflow-sequence mining and automation scoring.
- Redis-backed rate limiting, caching, and async ingestion queue.
- Background scheduler for retention cleanup and summary generation.

## Milestone 3 — hardening & scale

- Real agent packaging/signing + MSI installer; MDM deployment docs.
- SSO/SAML/OIDC for dashboard; per-org data-residency.
- Observability (metrics, tracing), alerting, and SLOs.
- Data-subject tooling (export/delete) and consent management UI.

## Testing strategy

- Backend: pytest with an isolated test DB (SQLite for unit, Postgres in CI).
- Safety-critical tests are mandatory and must pass: password fields never
  captured, secrets redacted before upload, cross-tenant access denied, device
  anti-impersonation, content-version dedup.
- Extension: unit tests for the redaction/URL-sanitization port.
