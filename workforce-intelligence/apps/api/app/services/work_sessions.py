"""Work-session engine.

Groups ordered activity/browser events into logical work sessions using
deterministic rules. The ``SessionClassifier`` interface is intentionally
pluggable so an AI classifier can later improve inference without changing
callers (see ARCHITECTURE.md §5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActivityEvent, BrowserEvent, WorkSession


@dataclass
class FocusInterval:
    started_at: datetime
    ended_at: datetime
    active_seconds: int
    kind: str  # "application" | "website"
    label: str  # app name or domain
    detail: str  # window/page title


@dataclass
class SessionDraft:
    started_at: datetime
    ended_at: datetime
    active_seconds: int = 0
    apps: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)


# ── Deterministic domain → marketing system mapping ───────────────────────────
DOMAIN_SYSTEM: dict[str, str] = {
    "hubspot.com": "HubSpot CRM",
    "app.hubspot.com": "HubSpot CRM",
    "business.facebook.com": "Meta Ads Manager",
    "facebook.com": "Meta Ads Manager",
    "ads.google.com": "Google Ads",
    "linkedin.com": "LinkedIn Campaign Manager",
    "docs.google.com": "Google Docs",
    "mail.google.com": "Gmail",
    "outlook.office.com": "Outlook",
}


def system_for_domain(domain: str) -> str | None:
    d = domain.lower()
    for key, name in DOMAIN_SYSTEM.items():
        if d == key or d.endswith("." + key):
            return name
    return None


class SessionClassifier(Protocol):
    """Infers (customer, campaign, task) for a session. Replaceable by AI later."""

    def classify(self, draft: SessionDraft) -> dict[str, str | None]: ...


class DeterministicClassifier:
    """Rule-based inference. No AI required."""

    def classify(self, draft: SessionDraft) -> dict[str, str | None]:
        systems = sorted({s for d in draft.domains if (s := system_for_domain(d))})
        task: str | None = None
        if "Meta Ads Manager" in systems:
            task = "Create/manage Meta campaign"
        elif "Google Ads" in systems:
            task = "Create/manage Google Ads campaign"
        elif "LinkedIn Campaign Manager" in systems:
            task = "Create/manage LinkedIn campaign"
        elif "HubSpot CRM" in systems:
            task = "CRM / customer management"
        elif "Google Docs" in systems:
            task = "Draft business content"
        elif systems:
            task = f"Work in {systems[0]}"

        # Best-effort campaign hint from titles containing the word "campaign".
        campaign = None
        for t in draft.titles:
            low = t.lower()
            if "campaign" in low:
                campaign = t.strip()[:120]
                break
        return {"inferred_customer": None, "inferred_campaign": campaign, "inferred_task": task}


def _collect_intervals(db: Session, employee_id: str, start: datetime, end: datetime) -> list[FocusInterval]:
    intervals: list[FocusInterval] = []
    acts = db.execute(
        select(ActivityEvent).where(
            ActivityEvent.employee_id == employee_id,
            ActivityEvent.started_at >= start,
            ActivityEvent.started_at < end,
            ActivityEvent.is_idle == False,  # noqa: E712 (idle time isn't work)
        )
    ).scalars()
    for a in acts:
        intervals.append(
            FocusInterval(a.started_at, a.ended_at, a.active_seconds, "application", a.application, a.window_title)
        )
    brs = db.execute(
        select(BrowserEvent).where(
            BrowserEvent.employee_id == employee_id,
            BrowserEvent.started_at >= start,
            BrowserEvent.started_at < end,
        )
    ).scalars()
    for b in brs:
        intervals.append(
            FocusInterval(b.started_at, b.ended_at, b.active_seconds, "website", b.domain, b.page_title)
        )
    intervals.sort(key=lambda i: i.started_at)
    return intervals


def build_sessions(
    db: Session,
    organization_id: str,
    employee_id: str,
    start: datetime,
    end: datetime,
    classifier: SessionClassifier | None = None,
    persist: bool = True,
) -> list[WorkSession]:
    """Rebuild work sessions for an employee in [start, end)."""
    if classifier is None:
        # Lazy import avoids a circular import (classifier imports this module).
        from app.services.ai.classifier import get_default_classifier

        classifier = get_default_classifier()
    break_gap = get_settings().session_idle_break_seconds
    intervals = _collect_intervals(db, employee_id, start, end)

    drafts: list[SessionDraft] = []
    cur: SessionDraft | None = None
    prev_end: datetime | None = None
    for iv in intervals:
        new_day = prev_end is not None and iv.started_at.date() != prev_end.date()
        gap = (iv.started_at - prev_end).total_seconds() if prev_end else 0
        if cur is None or new_day or gap > break_gap:
            cur = SessionDraft(started_at=iv.started_at, ended_at=iv.ended_at)
            drafts.append(cur)
        cur.ended_at = max(cur.ended_at, iv.ended_at)
        cur.active_seconds += max(0, iv.active_seconds)
        if iv.kind == "application" and iv.label:
            cur.apps.add(iv.label)
        if iv.kind == "website" and iv.label:
            cur.domains.add(iv.label)
        if iv.detail:
            cur.titles.append(iv.detail)
        prev_end = iv.ended_at

    sessions: list[WorkSession] = []
    for d in drafts:
        inferred = classifier.classify(d)
        ws = WorkSession(
            organization_id=organization_id,
            employee_id=employee_id,
            started_at=d.started_at,
            ended_at=d.ended_at,
            active_seconds=d.active_seconds,
            apps=",".join(sorted(d.apps)),
            domains=",".join(sorted(d.domains)),
            inferred_customer=inferred.get("inferred_customer"),
            inferred_campaign=inferred.get("inferred_campaign"),
            inferred_task=inferred.get("inferred_task"),
        )
        sessions.append(ws)

    if persist:
        # Replace existing sessions in the window to stay idempotent.
        existing = db.execute(
            select(WorkSession).where(
                WorkSession.employee_id == employee_id,
                WorkSession.started_at >= start,
                WorkSession.started_at < end,
            )
        ).scalars().all()
        for e in existing:
            db.delete(e)
        for ws in sessions:
            db.add(ws)
        db.commit()
        for ws in sessions:
            db.refresh(ws)
    return sessions
