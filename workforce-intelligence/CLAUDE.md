# CLAUDE.md — guardrails for contributors and AI assistants

This repository is a **transparent, consent-based workforce-analytics
platform** for **company-owned** devices. Read [`SECURITY.md`](./SECURITY.md)
and [`ARCHITECTURE.md`](./ARCHITECTURE.md) before changing collector or
ingestion code.

## Non-negotiable invariants

1. **Collectors are outbound-only.** There is no backend→workstation command,
   script, or control channel. Never add a command endpoint, remote
   "executor", remote shell, or anything that runs code received from the
   network on a workstation. Backend responses are acknowledgements and
   non-executable config (allowlist, intervals) consumed strictly as data.
2. **Metadata, not keystrokes.** The agent collects active app/window/title,
   durations, idle/lock state, heartbeat — never typed characters, never
   process memory, never screenshots.
3. **No secrets, ever.** `input[type="password"]` and credential/secret/MFA/
   payment fields are never read. Redaction runs on the workstation before
   upload and again on the server. URL query secrets are stripped.
4. **Content capture is allowlist-gated** and off by default. Only explicitly
   approved business domains capture business text.
5. **Agent is visible.** It appears in installed applications and is removable
   with the normal OS uninstaller. No stealth, no hidden processes, no
   persistence-evasion, no AV bypass.
6. **Tenant isolation + RBAC on every endpoint.** Every tenant-scoped query is
   filtered by `organization_id`. The AI layer never gets direct DB access.
7. **Device-derived identity.** The server trusts the device credential, not a
   client-supplied `employee_id`.

If a change would weaken any of the above, stop and reconsider — that is out of
scope for this product by design.

## Conventions

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest.
- Dashboard: Next.js (App Router), React, TypeScript.
- Extension: TypeScript, Chrome Manifest V3 (Chrome + Edge).
- Agent: C# / .NET 8.
- Keep the SecretRedactor (Python) and its TypeScript port behaviorally aligned;
  add a test when you change redaction rules.
- Don't leave unmarked placeholder functions; mark intentional stubs clearly.

## Attribution

Follow the repository/host attribution guidance for commits and PRs. Do not put
any model identifier in committed artifacts (commit messages' Co-Authored-By
trailer excepted where the host requires it).
