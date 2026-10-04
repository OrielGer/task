"""Resolve which employees / organization a principal may see for analytics.

Centralizes the role → visible-employee mapping so every analytics/query
endpoint applies the same tenant + RBAC restriction.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import AuthContext
from app.models import Employee, Role, Team, TeamMember


def resolve_org(ctx: AuthContext, organization_id: str | None) -> str:
    """Determine the org scope for a request.

    Non-super-admins are pinned to their own org (any mismatch is 404).
    SUPER_ADMIN must pass ?organization_id=.
    """
    if ctx.role == Role.SUPER_ADMIN:
        if not organization_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "organization_id required")
        return organization_id
    if organization_id and organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if ctx.organization_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization in context")
    return ctx.organization_id


def visible_employee_ids(db: Session, ctx: AuthContext, organization_id: str) -> list[str]:
    role = ctx.role
    if role in (Role.SUPER_ADMIN, Role.ORG_ADMIN):
        rows = db.execute(
            select(Employee.id).where(Employee.organization_id == organization_id)
        ).scalars()
        return list(rows)
    if role == Role.MANAGER:
        rows = db.execute(
            select(TeamMember.employee_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.organization_id == organization_id,
                Team.manager_user_id == ctx.user_id,
            )
        ).scalars()
        return sorted(set(rows))
    if role == Role.EMPLOYEE:
        rows = db.execute(
            select(Employee.id).where(
                Employee.organization_id == organization_id,
                Employee.user_id == ctx.user_id,
            )
        ).scalars()
        return list(rows)
    return []


def parse_range(start: str | None, end: str | None, default_days: int = 7) -> tuple[datetime, datetime]:
    """Parse ISO date/datetime query params into a UTC [start, end) window."""
    if end:
        end_dt = _parse_dt(end)
    else:
        end_dt = datetime.now(UTC)
    if start:
        start_dt = _parse_dt(start)
    else:
        start_dt = end_dt - timedelta(days=default_days)
    if start_dt >= end_dt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "start must be before end")
    return start_dt, end_dt


def _parse_dt(value: str) -> datetime:
    try:
        if len(value) == 10:  # YYYY-MM-DD
            dt = datetime.strptime(value, "%Y-%m-%d")
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid date: {value}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
