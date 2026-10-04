"""Test harness: isolated SQLite DB + provisioning helpers.

The DATABASE_URL and a strong JWT secret are set BEFORE importing the app so the
engine/session bind to the test database.
"""
from __future__ import annotations

import os
import secrets as _secrets
import tempfile
import uuid
from dataclasses import dataclass

import pytest

_TEST_DB = os.path.join(tempfile.gettempdir(), f"wfi_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DB}"
os.environ["JWT_SECRET"] = _secrets.token_hex(32)
os.environ["AI_PROVIDER"] = "mock"
os.environ.setdefault("RATE_LIMIT_REQUESTS", "100000")  # don't rate-limit tests

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Device,
    Employee,
    EmployeeStatus,
    Organization,
    Role,
    Team,
    TeamMember,
    User,
)
from app.security import hash_device_secret, hash_password


@dataclass
class OrgBundle:
    org_id: str
    admin_token: str = ""
    manager_token: str = ""
    employee_token: str = ""
    manager_user_id: str = ""
    employee_user_id: str = ""
    employee_id: str = ""  # Employee linked to employee_user
    other_employee_id: str = ""  # Employee NOT on the manager's team
    team_id: str = ""
    device_key: str = ""
    device_secret: str = ""
    device_id: str = ""


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def provision_org(client: TestClient, name: str, *, with_device: bool = True) -> OrgBundle:
    """Create org + admin/manager/employee + team + two employees (+ device).

    Done directly via the ORM for deterministic setup; behaviors under test are
    exercised through the HTTP API.
    """
    db = SessionLocal()
    try:
        org = Organization(
            name=name, allowlisted_domains="docs.google.com,app.hubspot.com"
        )
        db.add(org)
        db.flush()

        admin = User(
            organization_id=org.id, email=f"admin_{uuid.uuid4().hex[:6]}@{name.lower()}.example",
            password_hash=hash_password("Admin!pass1"), role=Role.ORG_ADMIN, full_name="Admin",
        )
        manager = User(
            organization_id=org.id, email=f"mgr_{uuid.uuid4().hex[:6]}@{name.lower()}.example",
            password_hash=hash_password("Mgr!pass1"), role=Role.MANAGER, full_name="Manager",
        )
        emp_user = User(
            organization_id=org.id, email=f"emp_{uuid.uuid4().hex[:6]}@{name.lower()}.example",
            password_hash=hash_password("Emp!pass1"), role=Role.EMPLOYEE, full_name="Employee",
        )
        db.add_all([admin, manager, emp_user])
        db.flush()

        emp = Employee(
            organization_id=org.id, user_id=emp_user.id, display_name="Employee One",
            status=EmployeeStatus.active,
        )
        other = Employee(
            organization_id=org.id, display_name="Employee Two", status=EmployeeStatus.offline
        )
        db.add_all([emp, other])
        db.flush()

        team = Team(organization_id=org.id, name="Team A", manager_user_id=manager.id)
        db.add(team)
        db.flush()
        # Only `emp` is on the manager's team; `other` is not.
        db.add(TeamMember(organization_id=org.id, team_id=team.id, employee_id=emp.id))

        bundle = OrgBundle(
            org_id=org.id,
            manager_user_id=manager.id,
            employee_user_id=emp_user.id,
            employee_id=emp.id,
            other_employee_id=other.id,
            team_id=team.id,
        )

        if with_device:
            key = "dev_" + uuid.uuid4().hex
            secret = _secrets.token_urlsafe(24)
            device = Device(
                organization_id=org.id, employee_id=emp.id, name="WS",
                device_key=key, credential_hash=hash_device_secret(secret), is_active=True,
            )
            db.add(device)
            db.flush()
            bundle.device_key = key
            bundle.device_secret = secret
            bundle.device_id = device.id

        admin_email, manager_email, emp_email = admin.email, manager.email, emp_user.email
        db.commit()
    finally:
        db.close()

    bundle.admin_token = _login(client, admin_email, "Admin!pass1")
    bundle.manager_token = _login(client, manager_email, "Mgr!pass1")
    bundle.employee_token = _login(client, emp_email, "Emp!pass1")
    return bundle


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def device_headers(bundle: OrgBundle) -> dict:
    return {"X-Device-Key": bundle.device_key, "X-Device-Secret": bundle.device_secret}
