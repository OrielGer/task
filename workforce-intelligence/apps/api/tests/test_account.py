"""Account endpoints: login-page options, password change, organization listing."""
from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Role, User
from app.security import hash_password
from tests.conftest import _login, auth, provision_org

CHANGE = "/api/v1/auth/change-password"


def _make_super_admin(client) -> str:
    db = SessionLocal()
    try:
        db.add(
            User(
                organization_id=None, email="root@platform.example", full_name="Root",
                password_hash=hash_password("Root!pass12"), role=Role.SUPER_ADMIN,
            )
        )
        db.commit()
    finally:
        db.close()
    return _login(client, "root@platform.example", "Root!pass12")


def test_auth_options_follow_seed_demo(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "seed_demo", True)
    assert client.get("/api/v1/auth/options").json() == {"demo_logins": True}
    monkeypatch.setattr(get_settings(), "seed_demo", False)
    assert client.get("/api/v1/auth/options").json() == {"demo_logins": False}


def test_change_password(client):
    b = provision_org(client, "orgA")
    email = client.get("/api/v1/auth/me", headers=auth(b.admin_token)).json()["email"]

    r = client.post(
        CHANGE, headers=auth(b.admin_token),
        json={"current_password": "Admin!pass1", "new_password": "N3w-strong-pass!"},
    )
    assert r.status_code == 204, r.text

    old = client.post("/api/v1/auth/login", json={"email": email, "password": "Admin!pass1"})
    assert old.status_code == 401
    new = client.post("/api/v1/auth/login", json={"email": email, "password": "N3w-strong-pass!"})
    assert new.status_code == 200

    db = SessionLocal()
    try:
        logged = db.execute(
            select(AuditLog).where(AuditLog.action == "change_password")
        ).scalars().all()
        assert len(logged) == 1
        assert logged[0].organization_id == b.org_id
    finally:
        db.close()


def test_change_password_rejects_bad_input(client):
    b = provision_org(client, "orgA")
    wrong = client.post(
        CHANGE, headers=auth(b.admin_token),
        json={"current_password": "not-my-password", "new_password": "N3w-strong-pass!"},
    )
    assert wrong.status_code == 400  # not 401: the dashboard would sign the user out
    weak = client.post(
        CHANGE, headers=auth(b.admin_token),
        json={"current_password": "Admin!pass1", "new_password": "short"},
    )
    assert weak.status_code == 422
    same = client.post(
        CHANGE, headers=auth(b.admin_token),
        json={"current_password": "Admin!pass1", "new_password": "Admin!pass1"},
    )
    assert same.status_code == 400


def test_change_password_requires_auth(client):
    r = client.post(CHANGE, json={"current_password": "x", "new_password": "N3w-strong-pass!"})
    assert r.status_code == 401


def test_list_organizations_is_scoped(client):
    a = provision_org(client, "orgA")
    b = provision_org(client, "orgB")
    root = _make_super_admin(client)

    everything = {o["id"] for o in client.get("/api/v1/organizations", headers=auth(root)).json()}
    assert {a.org_id, b.org_id} <= everything

    for token in (a.admin_token, a.manager_token, a.employee_token):
        own = client.get("/api/v1/organizations", headers=auth(token)).json()
        assert [o["id"] for o in own] == [a.org_id]
