"""Provisioning / administration endpoints (org, users, employees, teams, devices)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.db import get_db
from app.deps import (
    AuthContext,
    load_employee_or_404,
    require_roles,
    require_same_org,
)
from app.models import Device, Employee, Organization, Role, Team, TeamMember, User
from app.schemas import (
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    EmployeeCreate,
    EmployeeOut,
    OrganizationCreate,
    OrganizationOut,
    UserCreate,
)
from app.security import hash_device_secret, hash_password

router = APIRouter(prefix="/api/v1", tags=["admin"])

_ASSIGNABLE_ROLES = {Role.ORG_ADMIN, Role.MANAGER, Role.EMPLOYEE}


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    body: OrganizationCreate,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> Organization:
    org = Organization(name=body.name, allowlisted_domains=",".join(body.allowlisted_domains))
    db.add(org)
    db.commit()
    db.refresh(org)
    record_audit(
        db,
        organization_id=org.id,
        viewer_user_id=ctx.user_id,
        employee_id=None,
        action="create_organization",
        resource_type="organization",
        resource_id=org.id,
    )
    return org


@router.post("/organizations/{organization_id}/users", status_code=201)
def create_user(
    organization_id: str,
    body: UserCreate,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    require_same_org(ctx, organization_id)
    try:
        role = Role(body.role)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid role")
    if role not in _ASSIGNABLE_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Role not assignable here")
    # An ORG_ADMIN cannot mint another ORG_ADMIN unless they are one themselves
    # (they are, by the guard); SUPER_ADMIN unrestricted among assignable roles.
    exists = db.execute(
        select(User).where(User.organization_id == organization_id, User.email == body.email)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists in organization")
    user = User(
        organization_id=organization_id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "role": user.role.value}


@router.post("/organizations/{organization_id}/employees", response_model=EmployeeOut, status_code=201)
def create_employee(
    organization_id: str,
    body: EmployeeCreate,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> Employee:
    require_same_org(ctx, organization_id)
    if body.user_id is not None:
        linked = db.get(User, body.user_id)
        if linked is None or linked.organization_id != organization_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Linked user not in org")
    emp = Employee(
        organization_id=organization_id,
        display_name=body.display_name,
        email=body.email,
        user_id=body.user_id,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.post("/organizations/{organization_id}/teams", status_code=201)
def create_team(
    organization_id: str,
    name: str,
    manager_user_id: str | None = None,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    require_same_org(ctx, organization_id)
    if manager_user_id is not None:
        mgr = db.get(User, manager_user_id)
        if mgr is None or mgr.organization_id != organization_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Manager not in org")
    team = Team(organization_id=organization_id, name=name, manager_user_id=manager_user_id)
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "manager_user_id": team.manager_user_id}


@router.post("/teams/{team_id}/members", status_code=201)
def add_team_member(
    team_id: str,
    employee_id: str,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    require_same_org(ctx, team.organization_id)
    emp = load_employee_or_404(db, ctx, employee_id)
    if emp.organization_id != team.organization_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Employee not in team's org")
    tm = TeamMember(organization_id=team.organization_id, team_id=team_id, employee_id=employee_id)
    db.add(tm)
    db.commit()
    return {"id": tm.id, "team_id": team_id, "employee_id": employee_id}


@router.post("/organizations/{organization_id}/devices/enroll", response_model=DeviceEnrollResponse, status_code=201)
def enroll_device(
    organization_id: str,
    body: DeviceEnrollRequest,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> DeviceEnrollResponse:
    require_same_org(ctx, organization_id)
    emp = load_employee_or_404(db, ctx, body.employee_id)
    if emp.organization_id != organization_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Employee not in org")
    device_key = "dev_" + secrets.token_urlsafe(18)
    device_secret = secrets.token_urlsafe(32)
    device = Device(
        organization_id=organization_id,
        employee_id=emp.id,
        name=body.name,
        device_key=device_key,
        credential_hash=hash_device_secret(device_secret),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    record_audit(
        db,
        organization_id=organization_id,
        viewer_user_id=ctx.user_id,
        employee_id=emp.id,
        action="enroll_device",
        resource_type="device",
        resource_id=device.id,
    )
    return DeviceEnrollResponse(
        device_id=device.id, device_key=device_key, device_secret=device_secret
    )


@router.post("/devices/{device_id}/revoke")
def revoke_device(
    device_id: str,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    require_same_org(ctx, device.organization_id)
    device.is_active = False
    db.commit()
    record_audit(
        db,
        organization_id=device.organization_id,
        viewer_user_id=ctx.user_id,
        employee_id=device.employee_id,
        action="revoke_device",
        resource_type="device",
        resource_id=device.id,
    )
    return {"id": device.id, "is_active": device.is_active}


@router.post("/jobs/{job_name}")
def run_job(
    job_name: str,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN)),
) -> dict:
    """Manually trigger a scheduled job (retention | summaries | automation)."""
    from app.services.scheduler import JOBS

    job = JOBS.get(job_name)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown job '{job_name}'")
    result = job()
    return {"job": job_name, "result": result}


@router.put("/organizations/{organization_id}/allowlist")
def set_allowlist(
    organization_id: str,
    domains: list[str],
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    require_same_org(ctx, organization_id)
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    cleaned = sorted({d.strip().lower() for d in domains if d.strip()})
    org.allowlisted_domains = ",".join(cleaned)
    db.commit()
    return {"organization_id": organization_id, "allowlisted_domains": cleaned}
