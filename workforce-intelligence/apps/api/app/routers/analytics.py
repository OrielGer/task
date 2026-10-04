"""Organization-wide analytics endpoints (tenant + role scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, get_current_user
from app.models import AutomationOpportunity, Role
from app.schemas import UsageRow
from app.scoping import parse_range, resolve_org, visible_employee_ids
from app.services import analytics as analytics_svc

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/apps", response_model=list[UsageRow])
def apps(
    organization_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    org = resolve_org(ctx, organization_id)
    ids = visible_employee_ids(db, ctx, org)
    s, e = parse_range(start, end)
    return analytics_svc.application_usage(db, org, ids, s, e)


@router.get("/websites", response_model=list[UsageRow])
def websites(
    organization_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    org = resolve_org(ctx, organization_id)
    ids = visible_employee_ids(db, ctx, org)
    s, e = parse_range(start, end)
    return analytics_svc.website_usage(db, org, ids, s, e)


@router.get("/workflows")
def workflows(
    organization_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    org = resolve_org(ctx, organization_id)
    ids = visible_employee_ids(db, ctx, org)
    s, e = parse_range(start, end, default_days=30)
    return analytics_svc.detect_workflows(db, org, ids, s, e)


@router.get("/automation")
def automation(
    organization_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Persisted automation opportunities.

    Admins recompute org-wide and get the fresh set; managers/employees read
    the persisted rows filtered to the employees they may see.
    """
    org = resolve_org(ctx, organization_id)
    ids = visible_employee_ids(db, ctx, org)
    s, e = parse_range(start, end, default_days=30)

    if ctx.role in (Role.SUPER_ADMIN, Role.ORG_ADMIN):
        rows = analytics_svc.recompute_automation_opportunities(db, org, ids, s, e)
    else:
        all_rows = db.execute(
            select(AutomationOpportunity).where(AutomationOpportunity.organization_id == org)
        ).scalars().all()
        visible = set(ids)
        rows = [
            r for r in all_rows
            if not r.employees or (set(r.employees.split(",")) & visible)
        ]
    return [
        {
            "id": r.id,
            "workflow_name": r.workflow_name,
            "occurrences_per_week": r.occurrences_per_week,
            "average_seconds": r.average_seconds,
            "employees": r.employees.split(",") if r.employees else [],
            "estimated_weekly_seconds": r.estimated_weekly_seconds,
            "automation_score": r.automation_score,
            "potential_weekly_savings_seconds": r.potential_weekly_savings_seconds,
        }
        for r in rows
    ]
