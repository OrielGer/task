"""Bootstrap management command tests."""
from __future__ import annotations

from app.manage import create_superadmin
from tests.conftest import auth  # noqa: F401  (ensures app import path)


def test_create_superadmin_and_login(client):
    rc = create_superadmin("root@platform.example", "Str0ng!bootstrap")
    assert rc == 0
    # The new SUPER_ADMIN can authenticate.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "root@platform.example", "password": "Str0ng!bootstrap"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "SUPER_ADMIN"
    assert r.json()["organization_id"] is None


def test_create_superadmin_idempotent(client):
    assert create_superadmin("dup@platform.example", "pw-one-123") == 0
    # Second call no-ops (does not error, does not change the password).
    assert create_superadmin("dup@platform.example", "pw-two-456") == 0
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "dup@platform.example", "password": "pw-one-123"},
    )
    assert r.status_code == 200


def test_create_superadmin_requires_fields(client):
    assert create_superadmin("", "pw") == 2
