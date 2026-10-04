# Workforce Intelligence — Dashboard

A read-only analytics UI for the transparent, consent-based workforce-analytics
platform. It renders data served by the backend API. All business content is
**already redacted server-side**; this app only displays it. There is no write
path and no raw-secret display — it is analytics only.

Built with Next.js (App Router) + React + TypeScript, intentionally
dependency-light: just `next`, `react`, `react-dom` at runtime and `typescript`
+ type packages for development. No UI kit, no data-fetching library — plain
`fetch` and a single global stylesheet.

## Getting started

```bash
npm install

# Point at your API (defaults to http://localhost:8000 if unset)
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

npm run dev        # http://localhost:3000
```

Other scripts:

```bash
npm run build      # production build
npm run start      # serve the production build on port 3000
npm run typecheck  # tsc --noEmit
```

### Configuration

| Variable                   | Default                 | Purpose              |
| -------------------------- | ----------------------- | -------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |

The variable is read at build time (it is a `NEXT_PUBLIC_*` value), so set it
before `npm run dev` / `npm run build`.

## Demo logins

With the backend seeded (see `apps/api`), these accounts are available:

| Role     | Email                 | Password        |
| -------- | --------------------- | --------------- |
| Admin    | `admin@acme.example`  | `Passw0rd!admin` |
| Manager  | `manager@acme.example`| `Passw0rd!mgr`   |
| Employee | `daniel@acme.example` | `Passw0rd!emp`   |

What each role can see is enforced by the API (tenant isolation + RBAC); the
dashboard simply renders whatever the API returns for the signed-in user.

## Authentication

Login calls `POST /api/v1/auth/login` and stores the returned JWT in
`localStorage`. Every API request sends it as `Authorization: Bearer <token>`.
If a request returns `401`, or there is no token, the app clears the session and
redirects to `/login`.

## Pages

- `/login` — email + password; stores the token and redirects to `/`.
- `/` — organization overview: Active / Idle / Offline counts and an employee
  table (name, status, activity hint, last seen) linking to each employee.
- `/employees/[id]` — per-employee view with a day picker (defaults to today):
  current status, daily timeline, application + website usage, work sessions
  (with inferred customer / campaign / task), business content with per-item
  **version history and a line diff** between consecutive versions
  (v1 → v2 → final), the daily AI summary, and AI recommendations (insights
  with severity + recommendation).
- `/analytics` — organization-wide Applications, Websites, and Workflows
  (workflow name, occurrences/week, average duration, automation score as a
  percentage, and potential weekly time saving).
- `/ai` — chat-style assistant posting to `POST /api/v1/ai/query`; each answer
  shows the scope used and the AI provider. Optional employee/team scoping.

## Project layout

```
app/
  layout.tsx            # root layout + AuthProvider + header
  globals.css           # the single stylesheet
  page.tsx              # organization overview ("/")
  login/page.tsx
  analytics/page.tsx
  ai/page.tsx
  employees/[id]/page.tsx
components/
  Nav.tsx               # header with navigation + logout
  Protected.tsx         # auth guard wrapper
  ContentPanel.tsx      # business content + version-history diffs
  ui.tsx                # badges, usage bars, loading/error states
lib/
  api.ts                # typed fetch client + token handling
  auth.tsx              # client auth context (token in localStorage)
  types.ts              # TS interfaces mirroring the API
  format.ts             # duration/time/percent helpers
  diff.ts               # dependency-free line diff
```

## Security notes

- Read-only: the UI performs no writes beyond authenticating and querying.
- Content shown is redacted by the backend before it ever reaches the client;
  the dashboard adds no code path that would reveal raw secrets.
- The token lives only in the browser's `localStorage` and is sent solely to the
  configured API base URL.
