"""Automation agents: templates, RBAC/tenancy, sandbox runs, review, suggestions."""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, AutomationOpportunity
from app.services import automation_agents as svc
from tests.conftest import auth, provision_org

BASE = "/api/v1/automation"


def _create(client, token, template="campaign_report", **extra):
    return client.post(f"{BASE}/agents", headers=auth(token), json={"template": template, **extra})


def _add_opportunity(org_id: str, workflow: str, savings: int = 3600) -> None:
    db = SessionLocal()
    try:
        db.add(
            AutomationOpportunity(
                organization_id=org_id, workflow_name=workflow, occurrences_per_week=5,
                average_seconds=600, estimated_weekly_seconds=3000, automation_score=0.8,
                potential_weekly_savings_seconds=savings,
            )
        )
        db.commit()
    finally:
        db.close()


def test_templates_listed_with_mode(client):
    b = provision_org(client, "orgA")
    r = client.get(f"{BASE}/templates", headers=auth(b.admin_token))
    assert r.status_code == 200
    body = r.json()
    assert {t["key"] for t in body["templates"]} == {
        "crm_ads_alignment", "stakeholder_update", "campaign_report", "campaign_watch",
    }
    assert body["integration_mode"] == "sandbox"
    assert body["ai_provider"] == "mock"


def test_rbac_admin_manages_manager_views_employee_blocked(client):
    b = provision_org(client, "orgA")
    assert _create(client, b.manager_token).status_code == 403
    assert _create(client, b.employee_token).status_code == 403
    assert _create(client, b.admin_token).status_code == 201
    assert client.get(f"{BASE}/agents", headers=auth(b.manager_token)).status_code == 200
    assert client.get(f"{BASE}/agents", headers=auth(b.employee_token)).status_code == 403


def test_unknown_template_rejected(client):
    b = provision_org(client, "orgA")
    assert _create(client, b.admin_token, template="does_not_exist").status_code == 422


def test_sandbox_run_then_approve_credits_minutes(client):
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token, template="campaign_report").json()
    assert agent["name"] == "Cross-channel campaign report"
    assert agent["minutes_saved_per_run"] == 45

    run = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token))
    assert run.status_code == 201, run.text
    run = run.json()
    assert run["status"] == "awaiting_approval"
    assert run["sandbox"] is True
    reads = [s for s in run["steps"] if s["name"].startswith("Read ")]
    assert len(reads) == 3 and all(s["status"] == "done" for s in reads)
    ai = next(s for s in run["steps"] if s["name"] == "AI rewrite")
    assert ai["status"] == "skipped"  # mock provider → deterministic draft kept
    assert "Acme Q4 Awareness" in run["output"]
    assert "Total: 6 campaigns, 3 running, 3 not running." in run["output"]

    ok = client.post(f"{BASE}/runs/{run['id']}/approve", headers=auth(b.admin_token))
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved" and ok.json()["minutes_saved"] == 45
    again = client.post(f"{BASE}/runs/{run['id']}/approve", headers=auth(b.admin_token))
    assert again.status_code == 409

    listed = client.get(f"{BASE}/agents", headers=auth(b.admin_token)).json()
    assert listed[0]["runs"] == 1 and listed[0]["minutes_saved"] == 45
    assert listed[0]["awaiting_approval"] == 0

    db = SessionLocal()
    try:
        actions = set(db.execute(select(AuditLog.action)).scalars())
        assert {"create_automation_agent", "run_automation_agent", "approve_agent_run"} <= actions
    finally:
        db.close()


def test_reject_credits_nothing(client):
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token, template="campaign_watch").json()
    run = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token)).json()
    assert "3 of 6 campaigns are not running" in run["output"]
    rej = client.post(f"{BASE}/runs/{run['id']}/reject", headers=auth(b.admin_token)).json()
    assert rej["status"] == "rejected" and rej["minutes_saved"] == 0
    runs = client.get(f"{BASE}/agents/{agent['id']}/runs", headers=auth(b.manager_token))
    assert runs.status_code == 200 and runs.json()[0]["status"] == "rejected"


def test_crm_ads_alignment_matches_campaigns_across_systems(client):
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token, template="crm_ads_alignment").json()
    out = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token)).json()["output"]
    assert "Compared 2 CRM campaigns with 2 Meta Ads campaigns." in out
    assert "In sync:" in out and "To create:" not in out
    assert "nothing was changed in HubSpot or Meta Ads" in out


def test_paused_agent_cannot_run(client):
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token).json()
    p = client.patch(f"{BASE}/agents/{agent['id']}", headers=auth(b.admin_token), json={"status": "paused"})
    assert p.status_code == 200 and p.json()["status"] == "paused"
    assert client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token)).status_code == 409


def test_cross_org_access_is_not_found(client):
    a = provision_org(client, "orgA")
    other = provision_org(client, "orgB")
    agent = _create(client, other.admin_token).json()
    run = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(other.admin_token)).json()
    assert client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(a.admin_token)).status_code == 404
    assert client.get(f"{BASE}/agents/{agent['id']}/runs", headers=auth(a.admin_token)).status_code == 404
    assert client.post(f"{BASE}/runs/{run['id']}/approve", headers=auth(a.admin_token)).status_code == 404
    assert client.get(f"{BASE}/agents", headers=auth(a.admin_token)).json() == []


def test_suggestions_map_workflows_to_templates(client):
    b = provision_org(client, "orgA")
    _add_opportunity(b.org_id, "HubSpot CRM → Meta Ads Manager → Google Docs", savings=7200)
    _add_opportunity(b.org_id, "Gmail → Google Ads → HubSpot CRM", savings=3600)
    _add_opportunity(b.org_id, "slack.com → notion.so → figma.com", savings=9000)  # no template
    r = client.get(f"{BASE}/suggestions", headers=auth(b.admin_token))
    assert r.status_code == 200
    got = {s["workflow_name"]: s["suggested_template"] for s in r.json()}
    assert got == {
        "HubSpot CRM → Meta Ads Manager → Google Docs": "crm_ads_alignment",
        "Gmail → Google Ads → HubSpot CRM": "stakeholder_update",
    }
    _create(client, b.admin_token, template="crm_ads_alignment",
            source_workflow="HubSpot CRM → Meta Ads Manager → Google Docs")
    covered = {s["workflow_name"]: s["has_agent"] for s in client.get(
        f"{BASE}/suggestions", headers=auth(b.admin_token)).json()}
    assert covered["HubSpot CRM → Meta Ads Manager → Google Docs"] is True
    assert covered["Gmail → Google Ads → HubSpot CRM"] is False
    assert client.get(f"{BASE}/suggestions", headers=auth(b.manager_token)).status_code == 403


def test_suggest_template_needs_two_systems():
    assert svc.suggest_template("Meta Ads Manager → figma.com") is None
    assert svc.suggest_template("Meta Ads Manager → Google Ads").key == "campaign_report"


def test_real_ai_provider_rewrites_and_output_is_redacted(client, monkeypatch):
    class FakeProvider:
        name = "anthropic"

        def complete(self, *, system, prompt, max_tokens=600):
            assert "Acme Q4 Awareness" in prompt  # the deterministic draft is the input
            return "Polished report. api_key=sk-THISSHOULDBEREDACTED123456"

    monkeypatch.setattr(svc, "get_provider", lambda: FakeProvider())
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token).json()
    run = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token)).json()
    assert run["provider"] == "anthropic"
    assert next(s for s in run["steps"] if s["name"] == "AI rewrite")["status"] == "done"
    assert run["output"].startswith("Polished report.")
    assert "sk-THISSHOULDBEREDACTED123456" not in run["output"]


def test_channel_failure_does_not_leak_request_url(client, monkeypatch):
    def boom(db, organization_id, channel):
        request = httpx.Request("GET", "https://graph.example/act_1/campaigns?access_token=SECRET123")
        raise httpx.HTTPStatusError("bad", request=request, response=httpx.Response(401, request=request))

    monkeypatch.setattr(svc.integrations, "fetch_campaigns", boom)
    b = provision_org(client, "orgA")
    agent = _create(client, b.admin_token).json()
    run = client.post(f"{BASE}/agents/{agent['id']}/run", headers=auth(b.admin_token)).json()
    assert run["status"] == "failed"
    assert all(s["status"] in ("failed", "skipped") for s in run["steps"])
    assert "SECRET123" not in str(run)
    assert "HTTP 401" in run["steps"][0]["detail"]
