# Workforce Intelligence Platform

A **transparent, consent-based workforce-analytics and marketing-productivity
platform** for **company-owned** Windows computers. It helps organizations
understand how marketing work gets done, surface inefficient workflows, and
recommend automation — using **activity metadata** and **business content on
explicitly allowlisted systems only**.

> This is **not** spyware. No keylogging, no password/credential/MFA/token
> capture, no screenshots, no webcam/mic, no stealth, no hidden processes, no
> remote command execution, no monitoring outside approved work apps. The agent
> is visible in installed applications and removable with the normal OS
> uninstaller. See **[SECURITY.md](./SECURITY.md)** for the full boundaries and
> threat model, and **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the design.

## Repository layout

```
workforce-intelligence/
  apps/
    api/               FastAPI backend (ingestion, RBAC, tenancy, AI, audit)
    dashboard/         Next.js web dashboard
    browser-extension/ Chrome/Edge MV3 extension (active tab + allowlisted content)
    windows-agent/     .NET 8 agent (activity metadata only)
  packages/
    shared-types/      Shared TS types (extension + dashboard)
  infra/               Infra helpers (DB init, etc.)
  scripts/             Dev/util scripts
  docker-compose.yml   Postgres + Redis + API + dashboard
  .env.example
  README.md  ARCHITECTURE.md  SECURITY.md  CLAUDE.md  IMPLEMENTATION_PLAN.md
  docs/                DATABASE.md, API.md
```

## Quick start (Docker)

```bash
cd workforce-intelligence
cp .env.example .env            # adjust secrets; defaults run locally
docker compose up --build
```

- API: http://localhost:8000  (OpenAPI docs at `/docs`)
- Dashboard: http://localhost:3000
- The API container runs migrations + seeds demo data on start.

### Demo logins (seeded)

| Role      | Email                    | Password      |
|-----------|--------------------------|---------------|
| ORG_ADMIN | admin@acme.example       | Passw0rd!admin|
| MANAGER   | manager@acme.example     | Passw0rd!mgr  |
| EMPLOYEE  | daniel@acme.example      | Passw0rd!emp  |

(Change or remove seed data before any real deployment.)

## Running the backend without Docker

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://wfi:wfi@localhost:5432/workforce_intelligence
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
pytest            # run the test suite (uses an isolated SQLite test DB)
```

## Browser extension (load unpacked)

```bash
cd apps/browser-extension
npm install
npm run build        # outputs dist/
```
Then in Chrome/Edge: `chrome://extensions` → enable *Developer mode* →
*Load unpacked* → select `apps/browser-extension/dist`. Configure the API URL,
device credential, and allowlist in the extension options page. See
[`apps/browser-extension/README.md`](./apps/browser-extension/README.md).

## Windows agent (install)

```powershell
cd apps\windows-agent
dotnet build -c Release
dotnet run --project WorkforceAgent   # dev run
```
Configure `appsettings.json` (API URL + device enrollment code). The agent is a
normal, visible Windows application. See
[`apps/windows-agent/README.md`](./apps/windows-agent/README.md).

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — system design & data flow
- [SECURITY.md](./SECURITY.md) — boundaries, controls, threat model
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) — milestones
- [docs/DATABASE.md](./docs/DATABASE.md) — schema reference
- [docs/API.md](./docs/API.md) — REST API reference
- [FEATURES.md](./FEATURES.md) — implemented features & next milestones
