"""Employee-centric read endpoints (timeline, usage, content, sessions, AI)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.db import get_db
from app.deps import (
    AuthContext,
    assert_can_view_employee,
    get_current_user,
    load_employee_or_404,
)
from app.models import ActivityEvent, BrowserEvent, ContentItem, ContentVersion, Employee
from app.schemas import (
    AIInsightOut,
    AISummaryOut,
    ContentItemOut,
    ContentVersionOut,
    CurrentActivity,
    EmployeeOut,
    TimelineEntry,
    UsageRow,
    WorkSessionOut,
)
from app.scoping import parse_range, resolve_org, visible_employee_ids
from app.services import analytics
from app.services.ai.services import ProductivityAnalysisService, WorkUnderstandingService
from app.services.work_sessions import build_sessions

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    organization_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Employee]:
    org = resolve_org(ctx, organization_id)
    ids = visible_employee_ids(db, ctx, org)
    if not ids:
        return []
    stmt = (
        select(Employee)
        .where(Employee.id.in_(ids))
        .order_by(Employee.display_name)
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars())


def _load_viewable(db: Session, ctx: AuthContext, employee_id: str) -> Employee:
    emp = load_employee_or_404(db, ctx, employee_id)
    assert_can_view_employee(db, ctx, emp)
    return emp


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee:
    return _load_viewable(db, ctx, employee_id)


@router.get("/{employee_id}/current", response_model=CurrentActivity)
def current_activity(
    employee_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentActivity:
    """The employee's most recent focus interval (application or website)."""
    emp = _load_viewable(db, ctx, employee_id)
    latest_app = db.execute(
        select(ActivityEvent).where(ActivityEvent.employee_id == emp.id)
        .order_by(ActivityEvent.ended_at.desc()).limit(1)
    ).scalar_one_or_none()
    latest_web = db.execute(
        select(BrowserEvent).where(BrowserEvent.employee_id == emp.id)
        .order_by(BrowserEvent.ended_at.desc()).limit(1)
    ).scalar_one_or_none()

    # Pick whichever ended most recently.
    chosen = None
    if latest_app and latest_web:
        chosen = latest_app if latest_app.ended_at >= latest_web.ended_at else latest_web
    else:
        chosen = latest_app or latest_web

    out = CurrentActivity(status=emp.status.value, last_seen_at=emp.last_seen_at)
    if chosen is not None:
        now = datetime.now(UTC)
        ended = chosen.ended_at
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=UTC)
        out.is_live = (now - ended).total_seconds() <= 300  # within 5 minutes
        out.since = chosen.started_at
        if isinstance(chosen, ActivityEvent):
            out.kind, out.label, out.detail = "application", chosen.application, chosen.window_title
        else:
            out.kind, out.label, out.detail = "website", chosen.domain, chosen.page_title
    return out


@router.get("/{employee_id}/timeline", response_model=list[TimelineEntry])
def timeline(
    employee_id: str,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TimelineEntry]:
    emp = _load_viewable(db, ctx, employee_id)
    s, e = parse_range(start, end, default_days=1)
    entries: list[TimelineEntry] = []
    for a in db.execute(
        select(ActivityEvent).where(
            ActivityEvent.employee_id == emp.id,
            ActivityEvent.started_at >= s,
            ActivityEvent.started_at < e,
        )
    ).scalars():
        entries.append(
            TimelineEntry(
                started_at=a.started_at, ended_at=a.ended_at, kind="application",
                label=a.application, detail=a.window_title, active_seconds=a.active_seconds,
            )
        )
    for b in db.execute(
        select(BrowserEvent).where(
            BrowserEvent.employee_id == emp.id,
            BrowserEvent.started_at >= s,
            BrowserEvent.started_at < e,
        )
    ).scalars():
        entries.append(
            TimelineEntry(
                started_at=b.started_at, ended_at=b.ended_at, kind="website",
                label=b.domain, detail=b.page_title, active_seconds=b.active_seconds,
            )
        )
    entries.sort(key=lambda x: x.started_at)
    return entries


@router.get("/{employee_id}/applications", response_model=list[UsageRow])
def applications(
    employee_id: str,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    emp = _load_viewable(db, ctx, employee_id)
    s, e = parse_range(start, end)
    return analytics.application_usage(db, emp.organization_id, [emp.id], s, e)


@router.get("/{employee_id}/websites", response_model=list[UsageRow])
def websites(
    employee_id: str,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    emp = _load_viewable(db, ctx, employee_id)
    s, e = parse_range(start, end)
    return analytics.website_usage(db, emp.organization_id, [emp.id], s, e)


@router.get("/{employee_id}/content", response_model=list[ContentItemOut])
def content_items(
    employee_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContentItem]:
    emp = _load_viewable(db, ctx, employee_id)
    record_audit(
        db, organization_id=emp.organization_id, viewer_user_id=ctx.user_id,
        employee_id=emp.id, action="view_content_list", resource_type="content_item",
    )
    return list(
        db.execute(
            select(ContentItem).where(ContentItem.employee_id == emp.id)
            .order_by(ContentItem.updated_at.desc())
        ).scalars()
    )


@router.get("/{employee_id}/content/{item_id}/versions", response_model=list[ContentVersionOut])
def content_versions(
    employee_id: str,
    item_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContentVersion]:
    emp = _load_viewable(db, ctx, employee_id)
    item = db.get(ContentItem, item_id)
    if item is None or item.employee_id != emp.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")
    record_audit(
        db, organization_id=emp.organization_id, viewer_user_id=ctx.user_id,
        employee_id=emp.id, action="view_content_history", resource_type="content_item",
        resource_id=item.id,
    )
    return list(
        db.execute(
            select(ContentVersion).where(ContentVersion.content_item_id == item.id)
            .order_by(ContentVersion.version_number)
        ).scalars()
    )


@router.get("/{employee_id}/sessions", response_model=list[WorkSessionOut])
def sessions(
    employee_id: str,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    emp = _load_viewable(db, ctx, employee_id)
    s, e = parse_range(start, end, default_days=1)
    return build_sessions(db, emp.organization_id, emp.id, s, e)


@router.get("/{employee_id}/insights", response_model=list[AIInsightOut])
def insights(
    employee_id: str,
    start: str | None = None,
    end: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    emp = _load_viewable(db, ctx, employee_id)
    s, e = parse_range(start, end, default_days=7)
    # Ensure sessions exist so workflow-based insights have input.
    build_sessions(db, emp.organization_id, emp.id, s, e)
    return ProductivityAnalysisService().generate_insights(db, emp, s, e)


@router.get("/{employee_id}/summary", response_model=AISummaryOut)
def summary(
    employee_id: str,
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today (UTC)"),
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AISummaryOut:
    emp = _load_viewable(db, ctx, employee_id)
    date_str = date or datetime.now(UTC).strftime("%Y-%m-%d")
    # Rebuild sessions for the day so the summary reflects current data.
    day_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    build_sessions(db, emp.organization_id, emp.id, day_start, day_start.replace(hour=23, minute=59, second=59))
    record_audit(
        db, organization_id=emp.organization_id, viewer_user_id=ctx.user_id,
        employee_id=emp.id, action="view_ai_summary", resource_type="ai_summary",
    )
    s = WorkUnderstandingService().daily_summary(db, emp, date_str)
    return AISummaryOut(employee_id=emp.id, date=date_str, summary=s.summary, provider=s.provider)
