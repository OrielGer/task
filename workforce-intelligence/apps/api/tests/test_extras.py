"""Tests for audit-driven fixes: team-activity RBAC, current activity,
SUPER_ADMIN /ai/query."""
from __future__ import annotations

from datetime import UTC, datetime

from app.manage import create_superadmin
from tests.conftest import auth, device_headers, provision_org


def _seed_one_event(client, b, title="HubSpot — Acme"):
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    client.post(
        "/api/v1/agent/events/batch",
        headers=device_headers(b),
        json={"events": [{
            "client_event_id": "cur1", "application": "chrome.exe", "window_title": title,
            "started_at": now, "ended_at": now, "active_seconds": 60,
            "is_idle": False, "is_locked": False,
        }]},
    )


# ── Team-activity RBAC (the audit's security finding) ─────────────────────────
def test_employee_cannot_read_team_activity(client):
    b = provision_org(client, "orgA")
    r = client.get(f"/api/v1/teams/{b.team_id}/activity", headers=auth(b.employee_token))
    assert r.status_code == 403


def test_manager_reads_own_team_activity(client):
    b = provision_org(client, "orgA")
    r = client.get(f"/api/v1/teams/{b.team_id}/activity", headers=auth(b.manager_token))
    assert r.status_code == 200
    assert r.json()["team_id"] == b.team_id


def test_admin_reads_team_activity(client):
    b = provision_org(client, "orgA")
    assert client.get(f"/api/v1/teams/{b.team_id}/activity", headers=auth(b.admin_token)).status_code == 200


def test_manager_cannot_read_other_org_team(client):
    a = provision_org(client, "orgA")
    other = provision_org(client, "orgB")
    r = client.get(f"/api/v1/teams/{other.team_id}/activity", headers=auth(a.manager_token))
    assert r.status_code == 404


# ── Current-activity endpoint ────────────────────────────────────────────────
def test_current_activity_reports_latest(client):
    b = provision_org(client, "orgA")
    _seed_one_event(client, b, title="Meta Ads Manager — Acme")
    r = client.get(f"/api/v1/employees/{b.employee_id}/current", headers=auth(b.admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "application"
    assert body["label"] == "chrome.exe"
    assert "Meta Ads Manager" in body["detail"]
    assert body["is_live"] is True


def test_current_activity_empty_when_no_events(client):
    b = provision_org(client, "orgA")
    r = client.get(f"/api/v1/employees/{b.other_employee_id}/current", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert r.json()["label"] is None


def test_current_activity_respects_rbac(client):
    b = provision_org(client, "orgA")
    r = client.get(f"/api/v1/employees/{b.other_employee_id}/current", headers=auth(b.employee_token))
    assert r.status_code == 403


# ── SUPER_ADMIN /ai/query (over-restrictive 400 fix) ─────────────────────────
def test_superadmin_ai_query_orgwide(client):
    b = provision_org(client, "orgA")
    assert create_superadmin("root@platform.example", "Str0ng!pw") == 0
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "root@platform.example", "password": "Str0ng!pw"},
    ).json()["access_token"]
    r = client.post(
        "/api/v1/ai/query",
        headers=auth(tok),
        json={"question": "Where is the team losing time?", "organization_id": b.org_id},
    )
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"


def test_superadmin_ai_query_specific_employee(client):
    b = provision_org(client, "orgA")
    create_superadmin("root2@platform.example", "Str0ng!pw2")
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "root2@platform.example", "password": "Str0ng!pw2"},
    ).json()["access_token"]
    # No organization_id needed — org is derived from the employee.
    r = client.post(
        "/api/v1/ai/query",
        headers=auth(tok),
        json={"question": "What did they work on?", "employee_id": b.employee_id},
    )
    assert r.status_code == 200
