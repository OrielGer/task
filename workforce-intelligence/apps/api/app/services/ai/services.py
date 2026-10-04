"""Logical AI services + the constrained AI query pipeline.

Pipeline (see ARCHITECTURE.md §6): the LLM never touches the DB. Callers do
authorization first, then these services run a whitelisted query plan, retrieve
tenant-scoped data, aggregate it, and only then hand a text context to the
provider. Model output is treated as text.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIInsight,
    AISummary,
    ContentItem,
    ContentVersion,
    Employee,
    WorkSession,
)
from app.services import analytics
from app.services.ai.provider import AIProvider, get_provider
from app.services.work_sessions import system_for_domain


def _day_bounds(date_str: str) -> tuple[datetime, datetime]:
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    return day, day + timedelta(days=1)


def _fmt_secs(seconds: int) -> str:
    m = seconds // 60
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60}m"


class WorkUnderstandingService:
    """Summarizes what an employee worked on."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def daily_summary(self, db: Session, emp: Employee, date_str: str) -> AISummary:
        start, end = _day_bounds(date_str)
        apps = analytics.application_usage(db, emp.organization_id, [emp.id], start, end)
        sites = analytics.website_usage(db, emp.organization_id, [emp.id], start, end)
        sessions = db.execute(
            select(WorkSession).where(
                WorkSession.employee_id == emp.id,
                WorkSession.started_at >= start,
                WorkSession.started_at < end,
            )
        ).scalars().all()

        context = [f"Employee: {emp.display_name}", f"Date: {date_str}"]
        context.append("Top applications: " + ", ".join(
            f"{a['label']} ({_fmt_secs(a['active_seconds'])})" for a in apps[:6]
        ) or "none")
        context.append("Top websites: " + ", ".join(
            f"{s['label']} ({_fmt_secs(s['active_seconds'])})" for s in sites[:6]
        ) or "none")
        context.append(f"Work sessions: {len(sessions)}")
        for ws in sessions[:8]:
            tasks = ws.inferred_task or "general work"
            context.append(
                f"- {ws.started_at:%H:%M}-{ws.ended_at:%H:%M} "
                f"({_fmt_secs(ws.active_seconds)}): {tasks}"
            )

        prompt = "\n".join(context)
        system = (
            "You summarize an individual's work day for a marketing team using "
            "ONLY the aggregated, work-focused data provided. Be concise, "
            "workflow-oriented, and never speculate about the person beyond the data."
        )
        answer = self.provider.complete(system=system, prompt=prompt)

        existing = db.execute(
            select(AISummary).where(
                AISummary.employee_id == emp.id, AISummary.summary_date == date_str
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = AISummary(
                organization_id=emp.organization_id,
                employee_id=emp.id,
                summary_date=date_str,
            )
            db.add(existing)
        existing.summary = answer
        existing.provider = self.provider.name
        db.commit()
        db.refresh(existing)
        return existing


class ProductivityAnalysisService:
    """Workflow/outcome-based inefficiency detection.

    Deliberately avoids naive surveillance metrics (e.g. keystroke counts).
    Signals are derived from workflow structure: context switching, repeated
    navigation between the same systems, likely manual copy/paste between
    systems, and long rework cycles in content.
    """

    def generate_insights(
        self, db: Session, emp: Employee, start: datetime, end: datetime
    ) -> list[AIInsight]:
        sessions = db.execute(
            select(WorkSession).where(
                WorkSession.employee_id == emp.id,
                WorkSession.started_at >= start,
                WorkSession.started_at < end,
            )
        ).scalars().all()

        insights: list[dict] = []

        # 1) Context switching: many distinct systems within single sessions.
        heavy_switch = [
            ws for ws in sessions
            if len(set(filter(None, (ws.apps + "," + ws.domains).split(",")))) >= 6
            and ws.active_seconds >= 600
        ]
        if heavy_switch:
            insights.append(
                {
                    "kind": "context_switching",
                    "title": "High context switching within work sessions",
                    "detail": (
                        f"{len(heavy_switch)} session(s) touched 6+ distinct apps/sites. "
                        "Frequent switching fragments focus and slows marketing output."
                    ),
                    "recommendation": (
                        "Batch similar tasks (e.g. all ad-copy edits, then all CRM "
                        "updates) and consider a single workspace/tab group per campaign."
                    ),
                    "severity": "medium",
                }
            )

        # 2) Likely manual copy/paste between two systems (A→B→A alternation).
        alternations = 0
        for ws in sessions:
            systems = [
                s for d in ws.domains.split(",")
                if d.strip() and (s := system_for_domain(d.strip()))
            ]
            for i in range(2, len(systems)):
                if systems[i] == systems[i - 2] and systems[i] != systems[i - 1]:
                    alternations += 1
        if alternations >= 3:
            insights.append(
                {
                    "kind": "manual_copy_paste",
                    "title": "Repeated back-and-forth between two systems",
                    "detail": (
                        f"Detected {alternations} A→B→A system alternations, a common "
                        "signature of manually copying data between tools."
                    ),
                    "recommendation": (
                        "Evaluate a direct integration or template so campaign details "
                        "flow from the CRM to the ads tool without manual re-entry."
                    ),
                    "severity": "high",
                }
            )

        # 3) Long rework cycles: content items with many revisions.
        items = db.execute(
            select(ContentItem).where(
                ContentItem.employee_id == emp.id,
                ContentItem.updated_at >= start,
                ContentItem.updated_at < end,
            )
        ).scalars().all()
        for item in items:
            vcount = db.execute(
                select(ContentVersion).where(ContentVersion.content_item_id == item.id)
            ).scalars().all()
            if len(vcount) >= 8:
                insights.append(
                    {
                        "kind": "excessive_rework",
                        "title": f"Many revisions on {item.content_type or 'content'}",
                        "detail": (
                            f"{len(vcount)} versions captured for one item on {item.domain}. "
                            "High revision counts can indicate unclear briefs or missing templates."
                        ),
                        "recommendation": (
                            "Start from an approved template and align on the brief/CTA before "
                            "drafting to reduce revision cycles."
                        ),
                        "severity": "low",
                    }
                )

        # Persist (replace previous insights in window to stay idempotent).
        prior = db.execute(
            select(AIInsight).where(
                AIInsight.employee_id == emp.id,
                AIInsight.created_at >= start,
                AIInsight.created_at < end,
            )
        ).scalars().all()
        for p in prior:
            db.delete(p)
        rows = [
            AIInsight(
                organization_id=emp.organization_id,
                employee_id=emp.id,
                kind=i["kind"],
                title=i["title"],
                detail=i["detail"],
                recommendation=i["recommendation"],
                severity=i["severity"],
            )
            for i in insights
        ]
        for r in rows:
            db.add(r)
        db.commit()
        for r in rows:
            db.refresh(r)
        return rows


class ContentAnalysisService:
    """Analyzes how business content evolved across versions."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def analyze_item(self, db: Session, item: ContentItem) -> str:
        versions = db.execute(
            select(ContentVersion)
            .where(ContentVersion.content_item_id == item.id)
            .order_by(ContentVersion.version_number)
        ).scalars().all()
        if not versions:
            return "No versions captured."
        ctx = [f"Content item on {item.domain} ({item.content_type}). {len(versions)} versions."]
        for v in versions:
            tag = " (final)" if v.is_final else ""
            ctx.append(f"v{v.version_number}{tag}: {v.content[:200]}")
        system = (
            "You analyze how a piece of marketing content evolved across versions "
            "using only the provided (already-redacted) text. Describe the trajectory "
            "(tone, specificity, CTA strength) in a few sentences."
        )
        return self.provider.complete(system=system, prompt="\n".join(ctx))


class WorkflowAnalysisService:
    """Identifies repeated workflows (wraps the deterministic detector)."""

    def analyze(
        self, db: Session, organization_id: str, employee_ids: list[str],
        start: datetime, end: datetime,
    ) -> list[dict]:
        return analytics.detect_workflows(db, organization_id, employee_ids, start, end)


class AutomationRecommendationService:
    """Turns detected workflows into ranked automation opportunities."""

    def recommend(
        self, db: Session, organization_id: str, employee_ids: list[str],
        start: datetime, end: datetime,
    ) -> list[dict]:
        workflows = analytics.detect_workflows(db, organization_id, employee_ids, start, end)
        out = []
        for w in workflows:
            out.append(
                {
                    **w,
                    "recommendation": (
                        f"Automate '{w['workflow_name']}': it runs ~{w['occurrences_per_week']}x/week "
                        f"at ~{_fmt_secs(w['average_seconds'])} each. Estimated automatable: "
                        f"{int(w['automation_score'] * 100)}% → potential saving "
                        f"{_fmt_secs(w['potential_weekly_savings_seconds'])}/week."
                    ),
                }
            )
        return out


class ManagerAssistantService:
    """Answers management questions via the constrained pipeline.

    Authorization (which employees the asker may see) is performed by the caller
    and passed in as ``employee_ids``. This service never reads outside that set.
    """

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def answer(
        self,
        db: Session,
        organization_id: str,
        employee_ids: list[str],
        question: str,
        start: datetime,
        end: datetime,
    ) -> tuple[str, str]:
        plan = _plan_query(question)
        context: list[str] = [f"Question: {question}", f"Scope: {len(employee_ids)} employee(s)."]

        if "apps" in plan:
            apps = analytics.application_usage(db, organization_id, employee_ids, start, end)
            context.append("Applications: " + ", ".join(
                f"{a['label']} {_fmt_secs(a['active_seconds'])}" for a in apps[:8]
            ))
        if "websites" in plan:
            sites = analytics.website_usage(db, organization_id, employee_ids, start, end)
            context.append("Websites: " + ", ".join(
                f"{s['label']} {_fmt_secs(s['active_seconds'])}" for s in sites[:8]
            ))
        if "workflows" in plan:
            wf = analytics.detect_workflows(db, organization_id, employee_ids, start, end)
            context.append("Top repeated workflows: " + "; ".join(
                f"{w['workflow_name']} (save {_fmt_secs(w['potential_weekly_savings_seconds'])}/wk)"
                for w in wf[:5]
            ))
        if "content" in plan:
            items = db.execute(
                select(ContentItem).where(
                    ContentItem.organization_id == organization_id,
                    ContentItem.employee_id.in_(employee_ids),
                    ContentItem.updated_at >= start,
                    ContentItem.updated_at < end,
                )
            ).scalars().all()
            context.append(f"Business content items: {len(items)} "
                           + ", ".join(sorted({i.content_type for i in items if i.content_type})[:6]))
        if "sessions" in plan:
            sessions = db.execute(
                select(WorkSession).where(
                    WorkSession.organization_id == organization_id,
                    WorkSession.employee_id.in_(employee_ids),
                    WorkSession.started_at >= start,
                    WorkSession.started_at < end,
                )
            ).scalars().all()
            tasks = Counter(ws.inferred_task for ws in sessions if ws.inferred_task)
            context.append("Session tasks: " + ", ".join(f"{t} x{c}" for t, c in tasks.most_common(6)))

        system = (
            "You are a marketing-operations analyst. Answer the manager's question "
            "using ONLY the aggregated, tenant-scoped data provided. Focus on "
            "workflows and outcomes, not raw activity volume. If the data is "
            "insufficient, say so plainly."
        )
        answer = self.provider.complete(system=system, prompt="\n".join(context))
        return answer, self.provider.name


_PLAN_KEYWORDS = {
    "apps": ("app", "application", "tool", "software", "use"),
    "websites": ("website", "site", "web", "domain", "visit", "page"),
    "workflows": ("workflow", "automate", "automation", "repetit", "repeat", "efficien", "losing time", "lose time"),
    "content": ("content", "copy", "wrote", "write", "draft", "create", "email", "ad "),
    "sessions": ("today", "work on", "worked on", "task", "customer", "campaign", "spend", "spent"),
}


def _plan_query(question: str) -> set[str]:
    q = question.lower()
    plan = {k for k, kws in _PLAN_KEYWORDS.items() if any(w in q for w in kws)}
    # Always include a baseline so vague questions still get useful context.
    if not plan:
        plan = {"apps", "websites", "sessions"}
    return plan
