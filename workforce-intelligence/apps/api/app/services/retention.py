"""Configurable retention cleanup jobs (see SECURITY.md §7)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ActivityEvent,
    AISummary,
    BrowserEvent,
    ContentVersion,
)


def run_retention(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Delete data older than the configured retention windows.

    Returns a count of rows deleted per category. Intended to be invoked by a
    scheduler (cron/Celery/APScheduler) in Milestone 2; exposed here as a pure
    function so it is easy to test and to call from a management command.
    """
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    def _cutoff(days: int) -> datetime:
        return now - timedelta(days=days)

    counts["activity_events"] = _purge(
        db, ActivityEvent, ActivityEvent.started_at < _cutoff(s.retention_activity_events_days)
    )
    counts["browser_events"] = _purge(
        db, BrowserEvent, BrowserEvent.started_at < _cutoff(s.retention_activity_events_days)
    )
    # Only non-final draft versions expire early; final versions follow analytics retention.
    counts["draft_versions"] = _purge(
        db,
        ContentVersion,
        (ContentVersion.is_final == False)  # noqa: E712
        & (ContentVersion.created_at < _cutoff(s.retention_content_versions_days)),
    )
    counts["ai_summaries"] = _purge(
        db, AISummary, AISummary.created_at < _cutoff(s.retention_ai_summaries_days)
    )
    db.commit()
    return counts


def _purge(db: Session, model, condition) -> int:
    result = db.execute(delete(model).where(condition))
    return result.rowcount or 0
