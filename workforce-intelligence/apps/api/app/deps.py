"""Authentication, RBAC, and tenant-isolation dependencies.

These are applied on every protected endpoint. Two kinds of principals exist:

* **Users** (dashboard/API) — Bearer JWT. Carry a role + organization_id.
* **Devices** (agent/extension) — device_key + device_secret headers. Identity
  (employee/org) is derived from the device record, never from the payload.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Device, Employee, Role, Team, TeamMember, User
from app.security import decode_access_token, verify_device_secret


# ── User auth ──────────────────────────────────────────────────────────────────
@dataclass
class AuthContext:
    user: User

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def organization_id(self) -> str | None:
        return self.user.organization_id

    @property
    def role(self) -> Role:
        return self.user.role


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or inactive user")
    return AuthContext(user=user)


def require_roles(*roles: Role):
    """Dependency factory enforcing that the current user has one of ``roles``."""

    allowed = set(roles)

    def _dep(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
        if ctx.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return ctx

    return _dep


# ── Tenant isolation helpers ───────────────────────────────────────────────────
def require_same_org(ctx: AuthContext, organization_id: str) -> None:
    """SUPER_ADMIN may cross orgs; everyone else is pinned to their own org."""
    if ctx.role == Role.SUPER_ADMIN:
        return
    if ctx.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def load_employee_or_404(db: Session, ctx: AuthContext, employee_id: str) -> Employee:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    # Tenant check first — a cross-org id must look identical to "not found".
    require_same_org(ctx, emp.organization_id)
    return emp


def assert_can_view_employee(db: Session, ctx: AuthContext, emp: Employee) -> None:
    """Role-scoped visibility on a specific employee (tenancy already checked)."""
    role = ctx.role
    if role in (Role.SUPER_ADMIN, Role.ORG_ADMIN):
        return
    if role == Role.EMPLOYEE:
        if emp.user_id == ctx.user_id:
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Employees may view only their own data")
    if role == Role.MANAGER:
        # The employee must belong to a team managed by this manager.
        stmt = (
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.employee_id == emp.id,
                TeamMember.organization_id == ctx.organization_id,
                Team.manager_user_id == ctx.user_id,
            )
            .limit(1)
        )
        if db.execute(stmt).first() is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Employee is not on your teams")
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")


def manager_team_or_403(db: Session, ctx: AuthContext, team_id: str) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    require_same_org(ctx, team.organization_id)
    if ctx.role == Role.MANAGER and team.manager_user_id != ctx.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your team")
    return team


# ── Device auth (agent/extension) ───────────────────────────────────────────────
def get_authenticated_device(
    x_device_key: str | None = Header(default=None),
    x_device_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Device:
    if not x_device_key or not x_device_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing device credentials")
    device = db.execute(
        select(Device).where(Device.device_key == x_device_key)
    ).scalar_one_or_none()
    if device is None or not device.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or revoked device")
    if not verify_device_secret(x_device_secret, device.credential_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device credentials")
    return device
