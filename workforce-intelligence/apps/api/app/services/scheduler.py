"""Background scheduler + job functions (retention, nightly summaries,
automation recompute).

Jobs are plain functions that open their own DB session, so they are easy to
test and to trigger manually. The APScheduler wiring is only started when
``SCHEDULER_ENABLED=true`` (off by default / in tests).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Employee, Organization
from app.services import analytics
from app.services.ai.services import WorkUnderstandingService
from app.services.retention import run_retention
from app.services.work_sessions import build_sessions

_scheduler = None


def job_retention() -> dict[str, int]:
    db = SessionLocal()
    try:
        return run_retention(db)
    finally:
        db.close()


def job_nightly_summaries(date_str: str | None = None) -> int:
    """Rebuild sessions and generate an AI daily summary per employee."""
    db = SessionLocal()
    count = 0
    try:
        date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        svc = WorkUnderstandingService()
        employees = db.execute(select(Employee)).scalars().all()
        for emp in employees:
            build_sessions(db, emp.organization_id, emp.id, day, day + timedelta(days=1))
            svc.daily_summary(db, emp, date_str)
            count += 1
        return count
    finally:
        db.close()


def job_automation_recompute(days: int = 30) -> int:
    db = SessionLocal()
    total = 0
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        orgs = db.execute(select(Organization.id)).scalars().all()
        for org_id in orgs:
            ids = db.execute(
                select(Employee.id).where(Employee.organization_id == org_id)
            ).scalars().all()
            rows = analytics.recompute_automation_opportunities(db, org_id, list(ids), start, end)
            total += len(rows)
        return total
    finally:
        db.close()


JOBS = {
    "retention": job_retention,
    "summaries": job_nightly_summaries,
    "automation": job_automation_recompute,
}


def start_scheduler():
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled or _scheduler is not None:
        return _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone="UTC")
    h = s.scheduler_summary_hour_utc
    sched.add_job(job_retention, "cron", hour=h, minute=0, id="retention")
    sched.add_job(job_nightly_summaries, "cron", hour=h, minute=10, id="summaries")
    sched.add_job(job_automation_recompute, "cron", hour=h, minute=20, id="automation")
    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
