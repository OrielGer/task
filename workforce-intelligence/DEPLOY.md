# Deployment

Three supported paths. For **your own server/VPS**, use Docker Compose
(§1) — it's one command. For managed hosting, use the **Render blueprint**
(§2) or **Fly.io** (§3). Do the **production hardening** in §4 first.

> The stack: PostgreSQL + Redis (optional) + the API (FastAPI) + the dashboard
> (Next.js). Collectors (Windows agent, browser extension) point at the API URL.

---

## 1. Your own server / VPS (Docker Compose) — recommended for self-hosting

Requires Docker + the Compose plugin on the server.

```bash
# On the server:
git clone https://github.com/OrielGer/task.git
cd task/workforce-intelligence

cp .env.example .env
# EDIT .env — at minimum (see §4):
#   POSTGRES_PASSWORD=<strong>
#   JWT_SECRET=$(openssl rand -hex 32)
#   INTEGRATION_ENC_KEY=$(openssl rand -hex 32)
#   SEED_DEMO=false                       # no demo accounts in production
#   CORS_ORIGINS=https://dashboard.your-domain.com
#   NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.com
#   AI_PROVIDER=mock                      # or openai/anthropic/gemini + key
#   SCHEDULER_ENABLED=true

docker compose up --build -d          # API :8000, dashboard :3000, Postgres :5432
docker compose logs -f api            # watch migrations run
```

The API container runs `alembic upgrade head` on boot. `python -m app.seed`
also runs but **no-ops when `SEED_DEMO=false`**, so production starts empty —
create your real org/users via the `/admin` dashboard page or the
`POST /api/v1/organizations/...` endpoints.

### TLS / reverse proxy
Terminate TLS at a reverse proxy (Caddy/Nginx/Traefik) in front of the two
services and route:
- `api.your-domain.com` → `127.0.0.1:8000`
- `dashboard.your-domain.com` → `127.0.0.1:3000`

Minimal Caddy example:
```
api.your-domain.com       { reverse_proxy 127.0.0.1:8000 }
dashboard.your-domain.com { reverse_proxy 127.0.0.1:3000 }
```
Then set `CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` to the https URLs and
`docker compose up -d --build` again (the dashboard bakes the API URL at build).

### Updating
```bash
git pull && docker compose up -d --build
```

---

## 2. Render (managed, one click) — `render.yaml` at the repo root

1. Push this repo to GitHub (done).
2. render.com → **New** → **Blueprint** → select the repo. Render reads
   `render.yaml` and provisions: a managed Postgres, `wfi-api`, `wfi-dashboard`.
   `JWT_SECRET` and `INTEGRATION_ENC_KEY` are auto-generated; `DATABASE_URL` is
   wired from the database; `SEED_DEMO=false`.
3. First deploy finishes with two URLs. Set the cross-URLs (marked
   `sync: false` in the blueprint) and redeploy:
   - `wfi-api` → `CORS_ORIGINS = https://wfi-dashboard.onrender.com`
   - `wfi-dashboard` → `NEXT_PUBLIC_API_BASE_URL = https://wfi-api.onrender.com`
   (trigger a dashboard redeploy so the API URL is baked in).

The API URL normalizes Render's `postgres://` DSN to psycopg automatically
(`Settings.sqlalchemy_database_url`).

---

## 3. Fly.io (managed, CLI)

Needs `flyctl` and a logged-in account (`fly auth login`).

```bash
# Postgres
fly postgres create --name wfi-db

# API
cd workforce-intelligence/apps/api
fly launch --no-deploy --name wfi-api            # generates fly.toml
fly postgres attach wfi-db --app wfi-api          # sets DATABASE_URL
fly secrets set --app wfi-api JWT_SECRET=$(openssl rand -hex 32) \
  INTEGRATION_ENC_KEY=$(openssl rand -hex 32) SEED_DEMO=false \
  AI_PROVIDER=mock INTEGRATION_MODE=sandbox SCHEDULER_ENABLED=true
# set the release/entrypoint to run migrations: alembic upgrade head && uvicorn ...
fly deploy --app wfi-api

# Dashboard
cd ../dashboard
fly launch --no-deploy --name wfi-dashboard
fly secrets set --app wfi-dashboard NEXT_PUBLIC_API_BASE_URL=https://wfi-api.fly.dev
fly deploy --app wfi-dashboard
# then set CORS_ORIGINS=https://wfi-dashboard.fly.dev on the API and redeploy it
```

---

## 4. Production hardening checklist (do before going live)

- [ ] `SEED_DEMO=false` — no demo accounts with known passwords.
- [ ] `JWT_SECRET` ≥ 32 random bytes (`openssl rand -hex 32`); unique per env.
- [ ] `INTEGRATION_ENC_KEY` set (dedicated, not the JWT secret).
- [ ] Strong `POSTGRES_PASSWORD` / managed DB with least-privilege creds.
- [ ] TLS everywhere; `CORS_ORIGINS` = exact dashboard origin (no `*`).
- [ ] `REDIS_URL` set so rate limiting is shared across instances.
- [ ] `AI_PROVIDER` + key only if you want real AI (defaults to offline mock).
- [ ] `INTEGRATION_MODE=live` + per-org tokens only when wiring real ad APIs.
- [ ] `SCHEDULER_ENABLED=true` on exactly one instance (retention + summaries).
- [ ] Back up Postgres; set the retention windows you need (see SECURITY.md §7).
- [ ] Deploy collectors (agent/extension) pointed at the API URL; enroll devices
      via `/admin`.

## First real tenant (no demo data)

A fresh production deploy has no users (seeding is off). Bootstrap the first
platform admin, then do everything else from the dashboard `/admin` page:

```bash
# Docker Compose:
docker compose exec api python -m app.manage create-superadmin \
  --email you@your-domain.com --password 'a-strong-password'

# Render/Fly: run the same in a one-off shell, or set WFI_ADMIN_EMAIL /
# WFI_ADMIN_PASSWORD env vars and run `python -m app.manage create-superadmin`.
```
The command is idempotent (no-ops if the email already exists). Then log in to
the dashboard as that SUPER_ADMIN → `/admin` → create an organization, an
ORG_ADMIN, employees, teams, enroll devices, and set the allowlist.
