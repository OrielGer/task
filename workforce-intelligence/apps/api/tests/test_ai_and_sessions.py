"""Work-session engine, AI summary/insights, and AI-query scope enforcement."""
from __future__ import annotations

from datetime import datetime, timezone

from tests.conftest import auth, device_headers, provision_org


def _seed_activity(client, b):
    now = datetime.now(timezone.utc)
    events = []
    plan = [
        ("chrome.exe", "HubSpot — Acme", 0),
        ("chrome.exe", "Google Docs — Acme brief", 300),
        ("chrome.exe", "Meta Ads Manager — Acme", 600),
    ]
    for i, (app, title, off) in enumerate(plan):
        start = now.replace(microsecond=0)
        events.append({
            "client_event_id": f"s{i}",
            "application": app,
            "window_title": title,
            "started_at": start.isoformat(),
            "ended_at": start.isoformat(),
            "active_seconds": 200,
            "is_idle": False,
            "is_locked": False,
        })
    client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": events})


def test_daily_summary_uses_mock_provider(client):
    b = provision_org(client, "orgA")
    _seed_activity(client, b)
    r = client.get(f"/api/v1/employees/{b.employee_id}/summary", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"
    assert r.json()["summary"]


def test_sessions_build(client):
    b = provision_org(client, "orgA")
    _seed_activity(client, b)
    r = client.get(f"/api/v1/employees/{b.employee_id}/sessions", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_insights_endpoint(client):
    b = provision_org(client, "orgA")
    _seed_activity(client, b)
    r = client.get(f"/api/v1/employees/{b.employee_id}/insights", headers=auth(b.admin_token))
    assert r.status_code == 200


def test_ai_query_rejects_out_of_scope_employee(client):
    b = provision_org(client, "orgA")
    # Manager asks about an employee NOT on their team → forbidden before any AI runs.
    r = client.post(
        "/api/v1/ai/query",
        headers=auth(b.manager_token),
        json={"question": "What did they work on?", "employee_id": b.other_employee_id},
    )
    assert r.status_code == 403


def test_ai_query_allows_in_scope_employee(client):
    b = provision_org(client, "orgA")
    _seed_activity(client, b)
    r = client.post(
        "/api/v1/ai/query",
        headers=auth(b.manager_token),
        json={"question": "What did they work on today?", "employee_id": b.employee_id},
    )
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"


def test_ai_query_cross_tenant_employee_404(client):
    a = provision_org(client, "orgA")
    other = provision_org(client, "orgB")
    r = client.post(
        "/api/v1/ai/query",
        headers=auth(a.admin_token),
        json={"question": "anything", "employee_id": other.employee_id},
    )
    assert r.status_code == 404
