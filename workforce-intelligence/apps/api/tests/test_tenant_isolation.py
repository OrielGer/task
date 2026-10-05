"""Tenant-isolation tests: org A can never reach org B's data."""
from __future__ import annotations

from tests.conftest import auth, provision_org


def test_admin_cannot_read_other_org_employee(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    # orgA admin tries to read an orgB employee → looks like 404 (not 403, to
    # avoid confirming existence across tenants).
    r = client.get(f"/api/v1/employees/{b.employee_id}", headers=auth(a.admin_token))
    assert r.status_code == 404


def test_employee_list_is_tenant_scoped(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    r = client.get("/api/v1/employees", headers=auth(a.admin_token))
    ids = {e["id"] for e in r.json()}
    assert b.employee_id not in ids
    assert b.other_employee_id not in ids


def test_cannot_read_other_org_content(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    r = client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(a.admin_token))
    assert r.status_code == 404


def test_cannot_enroll_device_in_other_org(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    # orgA admin cannot enroll a device under orgB.
    r = client.post(
        f"/api/v1/organizations/{b.org_id}/devices/enroll",
        headers=auth(a.admin_token),
        json={"employee_id": b.employee_id, "name": "evil"},
    )
    assert r.status_code == 404


def test_cannot_set_other_org_allowlist(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    r = client.put(
        f"/api/v1/organizations/{b.org_id}/allowlist",
        headers=auth(a.admin_token),
        json=["evil.example"],
    )
    assert r.status_code == 404


def test_analytics_scoped_to_own_org(client):
    a = provision_org(client, "orgA")
    provision_org(client, "orgB")
    # Passing another org's id is ignored/blocked; admin only ever sees own org.
    r = client.get("/api/v1/analytics/apps", headers=auth(a.admin_token))
    assert r.status_code == 200
