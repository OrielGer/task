# Database Schema

PostgreSQL in production; SQLite for unit tests. Primary keys are string UUIDs.
Every tenant-scoped table carries **`organization_id`**. The initial migration
(`apps/api/alembic/versions/0001_initial.py`) creates the schema from the ORM
metadata (`apps/api/app/models.py`), so the migrated schema cannot drift from
the models.

## Entity relationships

```
organizations 1─┬─< users              (login principals: role, org; NULL org only for SUPER_ADMIN)
                ├─< employees           (monitored person; optional link to a user for self-view)
                ├─< teams               (optional manager_user_id)
                ├─< team_members >────── employees        (team ↔ employee join)
                ├─< devices ───────────── employees        (enrolled workstation; credential hash)
                ├─< activity_events ───── employees, devices
                ├─< browser_events ────── employees, devices
                ├─< content_items ─┬───── employees
                │                  └─< content_versions    (version history)
                ├─< work_sessions ─────── employees
                ├─< ai_summaries ──────── employees
                ├─< ai_insights ───────── employees
                ├─< automation_opportunities
                └─< audit_logs
```

## Tables

### organizations
`id, name, allowlisted_domains (CSV), created_at, updated_at`
The allowlist gates business-text capture.

### users
`id, organization_id?, email, full_name, password_hash, role, is_active, created_at`
Unique `(organization_id, email)`. `role ∈ {SUPER_ADMIN, ORG_ADMIN, MANAGER, EMPLOYEE}`.
Passwords hashed with passlib (pbkdf2-sha256 default).

### employees
`id, organization_id, user_id?, display_name, email, status, last_seen_at?, created_at`
`status ∈ {active, idle, offline}`. `user_id` links an employee to a login user
(for EMPLOYEE self-view).

### teams / team_members
`teams: id, organization_id, name, manager_user_id?, created_at`
`team_members: id, organization_id, team_id, employee_id` (unique per pair).
A MANAGER sees exactly the employees on teams they manage.

### devices
`id, organization_id, employee_id, name, device_key (unique), credential_hash,
is_active, agent_version, last_heartbeat_at?, created_at`
`device_key` is public; the secret is stored only as `credential_hash`. The
server derives employee/org from this row — the agent cannot impersonate
another employee. `is_active=false` revokes the device.

### activity_events
`id, organization_id, employee_id, device_id, client_event_id, application,
window_title, started_at, ended_at, active_seconds, is_idle, is_locked,
created_at`
Unique `(device_id, client_event_id)` for idempotent batch retries. Window
titles are redacted on ingest. Index on `(employee_id, started_at)`.

### browser_events
`id, organization_id, employee_id, device_id, client_event_id, browser, domain,
url (sanitized), page_title, started_at, ended_at, active_seconds, focused,
created_at`
Active tab only. URLs are sanitized (sensitive params stripped) before storage.

### content_items / content_versions
`content_items: id, organization_id, employee_id, source, domain, url,
content_type, external_reference?, created_at, updated_at`
`content_versions: id, organization_id, content_item_id, version_number,
content (redacted), content_hash, is_final, created_at`
Unique `(content_item_id, content_hash)` so identical snapshots don't create a
new version. Only allowlisted-domain content is ever stored, after redaction.

### work_sessions
`id, organization_id, employee_id, started_at, ended_at, active_seconds, apps
(CSV), domains (CSV), inferred_customer?, inferred_campaign?, inferred_task?,
created_at`
Produced by the deterministic work-session engine.

### ai_summaries
`id, organization_id, employee_id, summary_date (YYYY-MM-DD), summary, provider,
created_at`

### ai_insights
`id, organization_id, employee_id, kind, title, detail, recommendation,
severity, created_at`

### automation_opportunities
`id, organization_id, workflow_name, occurrences_per_week, average_seconds,
employees (CSV), estimated_weekly_seconds, automation_score,
potential_weekly_savings_seconds, created_at`

### audit_logs
`id, organization_id?, viewer_user_id?, employee_id?, action, resource_type,
resource_id?, created_at`
One row per access to detailed employee content (and key admin actions).

## Retention (configurable; cleanup in `app/services/retention.py`)

| Data | Default |
|------|---------|
| activity_events / browser_events | 180 days |
| content_versions (non-final drafts) | 90 days |
| ai_summaries | 12 months |
| aggregated analytics | 24 months |
