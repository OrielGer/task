"""RBAC tests: each role sees only what it is allowed to."""
from __future__ import annotations

from tests.conftest import auth, provision_org


def test_employee_cannot_create_users(client):
    b = provision_org(client, "orgA")
    r = client.post(
        f"/api/v1/organizations/{b.org_id}/users",
        headers=auth(b.employee_token),
        json={"email": "x@orgA.example", "password": "pw123456", "role": "EMPLOYEE"},
    )
    assert r.status_code == 403


def test_manager_cannot_create_users(client):
    b = provision_org(client, "orgA")
    r = client.post(
        f"/api/v1/organizations/{b.org_id}/users",
        headers=auth(b.manager_token),
        json={"email": "y@orgA.example", "password": "pw123456", "role": "EMPLOYEE"},
    )
    assert r.status_code == 403


def test_admin_can_create_user(client):
    b = provision_org(client, "orgA")
    r = client.post(
        f"/api/v1/organizations/{b.org_id}/users",
        headers=auth(b.admin_token),
        json={"email": "new@orgA.example", "password": "pw123456", "role": "EMPLOYEE"},
    )
    assert r.status_code == 201, r.text


def test_employee_can_view_self_only(client):
    b = provision_org(client, "orgA")
    # own data OK
    r = client.get(f"/api/v1/employees/{b.employee_id}", headers=auth(b.employee_token))
    assert r.status_code == 200
    # another employee → forbidden
    r = client.get(f"/api/v1/employees/{b.other_employee_id}", headers=auth(b.employee_token))
    assert r.status_code == 403


def test_manager_sees_only_team_members(client):
    b = provision_org(client, "orgA")
    # team member OK
    r = client.get(f"/api/v1/employees/{b.employee_id}", headers=auth(b.manager_token))
    assert r.status_code == 200
    # non-team employee → forbidden
    r = client.get(f"/api/v1/employees/{b.other_employee_id}", headers=auth(b.manager_token))
    assert r.status_code == 403


def test_manager_employee_list_scoped_to_team(client):
    b = provision_org(client, "orgA")
    r = client.get("/api/v1/employees", headers=auth(b.manager_token))
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert b.employee_id in ids
    assert b.other_employee_id not in ids


def test_admin_sees_all_employees(client):
    b = provision_org(client, "orgA")
    r = client.get("/api/v1/employees", headers=auth(b.admin_token))
    ids = {e["id"] for e in r.json()}
    assert {b.employee_id, b.other_employee_id} <= ids


def test_unauthenticated_rejected(client):
    provision_org(client, "orgA")
    assert client.get("/api/v1/employees").status_code == 401
