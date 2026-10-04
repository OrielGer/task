"""Audit-log read endpoint (admins only), paginated."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, require_roles
from app.models import AuditLog, Role
from app.schemas import AuditLogOut, Page
from app.scoping import resolve_org

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=Page)
def list_audit(
    organization_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> Page:
    org = resolve_org(ctx, organization_id)
    base = select(AuditLog).where(AuditLog.organization_id == org)
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = db.execute(
        base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page(
        items=[AuditLogOut.model_validate(r).model_dump() for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )
