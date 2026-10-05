"""Audit endpoint + pagination tests."""
from __future__ import annotations

from tests.conftest import auth, provision_org


def test_audit_requires_admin(client):
    b = provision_org(client, "orgA")
    assert client.get("/api/v1/audit", headers=auth(b.employee_token)).status_code == 403
    assert client.get("/api/v1/audit", headers=auth(b.manager_token)).status_code == 403


def test_audit_records_content_access(client):
    b = provision_org(client, "orgA")
    # Viewing content writes an audit row.
    client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token))
    page = client.get("/api/v1/audit", headers=auth(b.admin_token)).json()
    assert page["total"] >= 1
    assert isinstance(page["items"], list)
    assert page["limit"] == 50 and page["offset"] == 0
    actions = {row["action"] for row in page["items"]}
    assert "view_content_list" in actions


def test_audit_is_tenant_scoped(client):
    a = provision_org(client, "orgA")
    bb = provision_org(client, "orgB")
    client.get(f"/api/v1/employees/{bb.employee_id}/content", headers=auth(bb.admin_token))
    # orgA admin must not see orgB audit rows.
    page = client.get("/api/v1/audit", headers=auth(a.admin_token)).json()
    assert all(row["employee_id"] != bb.employee_id for row in page["items"])


def test_audit_pagination(client):
    b = provision_org(client, "orgA")
    for _ in range(3):
        client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token))
    page = client.get("/api/v1/audit?limit=2&offset=0", headers=auth(b.admin_token)).json()
    assert len(page["items"]) <= 2
    assert page["total"] >= 3


def test_employee_list_pagination(client):
    b = provision_org(client, "orgA")
    r = client.get("/api/v1/employees?limit=1&offset=0", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert len(r.json()) == 1
