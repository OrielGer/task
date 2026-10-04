"""Team endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, manager_team_or_403, require_roles
from app.models import Employee, Role, TeamMember
from app.scoping import parse_range
from app.services import analytics

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("/{team_id}/activity")
def team_activity(
    team_id: str,
    start: str | None = None,
    end: str | None = None,
    # Team activity is for admins and managers only; EMPLOYEE is excluded
    # (an employee sees only their own data via /employees/{self}).
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN, Role.MANAGER)),
    db: Session = Depends(get_db),
) -> dict:
    # manager_team_or_403 further restricts MANAGER to teams they manage.
    team = manager_team_or_403(db, ctx, team_id)
    s, e = parse_range(start, end)
    emp_ids = list(
        db.execute(
            select(TeamMember.employee_id).where(TeamMember.team_id == team_id)
        ).scalars()
    )
    members = (
        list(db.execute(select(Employee).where(Employee.id.in_(emp_ids))).scalars())
        if emp_ids
        else []
    )
    return {
        "team_id": team_id,
        "team_name": team.name,
        "members": [{"id": m.id, "display_name": m.display_name, "status": m.status.value} for m in members],
        "applications": analytics.application_usage(db, team.organization_id, emp_ids, s, e),
        "websites": analytics.website_usage(db, team.organization_id, emp_ids, s, e),
    }
