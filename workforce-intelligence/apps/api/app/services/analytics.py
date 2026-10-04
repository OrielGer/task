"""Analytics aggregations: application usage, website usage, workflow mining.

All queries are tenant-scoped by ``organization_id`` and further restricted to
an explicit set of employee ids the caller is authorized to see.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ActivityEvent, AutomationOpportunity, BrowserEvent, WorkSession
from app.services.work_sessions import system_for_domain


def application_usage(
    db: Session,
    organization_id: str,
    employee_ids: list[str],
    start: datetime,
    end: datetime,
) -> list[dict]:
    if not employee_ids:
        return []
    rows = db.execute(
        select(
            ActivityEvent.application,
            func.sum(ActivityEvent.active_seconds),
            func.count(ActivityEvent.id),
        )
        .where(
            ActivityEvent.organization_id == organization_id,
            ActivityEvent.employee_id.in_(employee_ids),
            ActivityEvent.started_at >= start,
            ActivityEvent.started_at < end,
        )
        .group_by(ActivityEvent.application)
        .order_by(func.sum(ActivityEvent.active_seconds).desc())
    ).all()
    return [
        {"label": app or "(unknown)", "active_seconds": int(secs or 0), "event_count": int(cnt)}
        for app, secs, cnt in rows
    ]


def website_usage(
    db: Session,
    organization_id: str,
    employee_ids: list[str],
    start: datetime,
    end: datetime,
) -> list[dict]:
    if not employee_ids:
        return []
    rows = db.execute(
        select(
            BrowserEvent.domain,
            func.sum(BrowserEvent.active_seconds),
            func.count(BrowserEvent.id),
        )
        .where(
            BrowserEvent.organization_id == organization_id,
            BrowserEvent.employee_id.in_(employee_ids),
            BrowserEvent.started_at >= start,
            BrowserEvent.started_at < end,
        )
        .group_by(BrowserEvent.domain)
        .order_by(func.sum(BrowserEvent.active_seconds).desc())
    ).all()
    return [
        {"label": dom or "(unknown)", "active_seconds": int(secs or 0), "event_count": int(cnt)}
        for dom, secs, cnt in rows
    ]


def detect_workflows(
    db: Session,
    organization_id: str,
    employee_ids: list[str],
    start: datetime,
    end: datetime,
    min_occurrences: int = 2,
) -> list[dict]:
    """Deterministic repetitive-workflow detection.

    Builds per-session sequences of marketing *systems* (CRM, Ads Manager,
    Docs, …) and finds repeated contiguous sub-sequences (length >= 3). For
    each repeated workflow it estimates occurrences/week, average duration,
    the employees involved, total weekly time, an automation score, and the
    potential weekly time saving (see spec "Repetitive workflow detection").
    """
    if not employee_ids:
        return []

    sessions = db.execute(
        select(WorkSession).where(
            WorkSession.organization_id == organization_id,
            WorkSession.employee_id.in_(employee_ids),
            WorkSession.started_at >= start,
            WorkSession.started_at < end,
        )
    ).scalars().all()

    span_days = max(1, (end - start).days)
    weeks = max(1.0, span_days / 7.0)

    seq_durations: dict[tuple[str, ...], list[int]] = defaultdict(list)
    seq_employees: dict[tuple[str, ...], set[str]] = defaultdict(set)

    for ws in sessions:
        systems: list[str] = []
        for d in (ws.domains or "").split(","):
            d = d.strip()
            if not d:
                continue
            sysname = system_for_domain(d) or d
            if not systems or systems[-1] != sysname:
                systems.append(sysname)
        # Contiguous sub-sequences of length 3..5.
        for n in (3, 4, 5):
            for i in range(max(0, len(systems) - n + 1)):
                sub = tuple(systems[i : i + n])
                seq_durations[sub].append(ws.active_seconds or 0)
                seq_employees[sub].add(ws.employee_id)

    results: list[dict] = []
    for seq, durations in seq_durations.items():
        occ = len(durations)
        if occ < min_occurrences:
            continue
        avg = int(sum(durations) / occ)
        occ_per_week = occ / weeks
        weekly_seconds = int(avg * occ_per_week)
        # Heuristic automation score: more steps + more repetition → more automatable.
        score = min(0.95, 0.4 + 0.1 * len(seq) + 0.05 * occ)
        results.append(
            {
                "workflow_name": " → ".join(seq),
                "occurrences_per_week": round(occ_per_week, 1),
                "average_seconds": avg,
                "employees": sorted(seq_employees[seq]),
                "estimated_weekly_seconds": weekly_seconds,
                "automation_score": round(score, 2),
                "potential_weekly_savings_seconds": int(weekly_seconds * score),
            }
        )
    results.sort(key=lambda r: r["potential_weekly_savings_seconds"], reverse=True)
    return results[:25]


def recompute_automation_opportunities(
    db: Session,
    organization_id: str,
    employee_ids: list[str],
    start: datetime,
    end: datetime,
) -> list[AutomationOpportunity]:
    """Detect workflows and persist them as AutomationOpportunity rows.

    Replaces the organization's existing rows so the table reflects the latest
    analysis window. Intended for admins / the scheduler (org-wide input).
    """
    workflows = detect_workflows(db, organization_id, employee_ids, start, end)
    db.execute(
        delete(AutomationOpportunity).where(
            AutomationOpportunity.organization_id == organization_id
        )
    )
    rows: list[AutomationOpportunity] = []
    for w in workflows:
        row = AutomationOpportunity(
            organization_id=organization_id,
            workflow_name=w["workflow_name"][:255],
            occurrences_per_week=int(round(w["occurrences_per_week"])),
            average_seconds=w["average_seconds"],
            employees=",".join(w["employees"]),
            estimated_weekly_seconds=w["estimated_weekly_seconds"],
            automation_score=w["automation_score"],
            potential_weekly_savings_seconds=w["potential_weekly_savings_seconds"],
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows
