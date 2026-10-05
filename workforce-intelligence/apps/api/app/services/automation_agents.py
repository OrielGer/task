"""Automation agents: turn repetitive marketing workflows into reviewed drafts.

An agent is created from a TEMPLATE, optionally suggested by a repetitive
workflow that analytics detected (e.g. "HubSpot CRM → Meta Ads Manager").
Running it:

1. reads campaigns from the organization's integrations (read-only; sample
   data when INTEGRATION_MODE=sandbox),
2. builds a deterministic draft (report, status email, proposed changes),
3. rewrites it with the configured AI provider (skipped for the mock),
4. redacts it and stores it as a run that a person approves or rejects.

Agents never act on a workstation and never write to external systems. The
approved draft replaces the manual assembly work; approval credits the
template's estimated minutes saved.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentRun, AutomationAgent, AutomationOpportunity
from app.redaction import redact_text
from app.services import integrations
from app.services.ai.provider import get_provider
from app.services.integrations import CampaignRecord

CHANNEL_LABELS = {
    "meta": "Meta Ads",
    "google": "Google Ads",
    "linkedin": "LinkedIn Ads",
    "crm": "HubSpot CRM",
    "email": "Email",
}

# Workflow system names, as produced by services.work_sessions.DOMAIN_SYSTEM.
_ADS = frozenset({"Meta Ads Manager", "Google Ads", "LinkedIn Campaign Manager"})
_EMAIL = frozenset({"Gmail", "Outlook"})
_CRM = frozenset({"HubSpot CRM"})


@dataclass(frozen=True)
class AgentTemplate:
    key: str
    name: str
    description: str
    channels: tuple[str, ...]
    output_kind: str  # report | email_draft | change_proposal
    minutes_saved_per_run: int
    # Workflow systems that suggest this template, and systems it requires.
    match: frozenset[str]
    requires_any: frozenset[str] = frozenset()


TEMPLATES: tuple[AgentTemplate, ...] = (
    AgentTemplate(
        key="crm_ads_alignment",
        name="CRM → Ads alignment",
        description=(
            "Compares CRM campaigns with Meta Ads campaigns and proposes which to "
            "create or align, instead of copying details between the two by hand."
        ),
        channels=("crm", "meta"),
        output_kind="change_proposal",
        minutes_saved_per_run=30,
        match=_CRM | _ADS,
        requires_any=_CRM,
    ),
    AgentTemplate(
        key="stakeholder_update",
        name="Campaign status email",
        description=(
            "Drafts the recurring status email to stakeholders from current campaign "
            "data across the CRM and ad channels."
        ),
        channels=("crm", "meta", "google", "linkedin"),
        output_kind="email_draft",
        minutes_saved_per_run=20,
        match=_EMAIL | _ADS | _CRM,
        requires_any=_EMAIL,
    ),
    AgentTemplate(
        key="campaign_report",
        name="Cross-channel campaign report",
        description=(
            "Builds the campaign report (per channel: running vs. not running, every "
            "campaign listed) that is otherwise compiled by hand in a doc."
        ),
        channels=("meta", "google", "linkedin"),
        output_kind="report",
        minutes_saved_per_run=45,
        match=_ADS | {"Google Docs"},
    ),
    AgentTemplate(
        key="campaign_watch",
        name="Paused-campaign watch",
        description=(
            "Lists campaigns that are not running across the ad channels, so nobody "
            "has to check each ads manager by hand."
        ),
        channels=("meta", "google", "linkedin"),
        output_kind="report",
        minutes_saved_per_run=15,
        match=_ADS,
    ),
)
_BY_KEY = {t.key: t for t in TEMPLATES}


class AgentError(RuntimeError):
    """A run cannot be started or reviewed in the current state (HTTP 409)."""


def get_template(key: str) -> AgentTemplate | None:
    return _BY_KEY.get(key)


def suggest_template(workflow_name: str) -> AgentTemplate | None:
    """Best template for a detected workflow ("A → B → C"), or None.

    Needs at least two of the workflow's systems in the template's match set;
    ties go to the earlier template.
    """
    systems = {s.strip() for s in workflow_name.split("→") if s.strip()}
    best: AgentTemplate | None = None
    best_score = 1
    for t in TEMPLATES:
        if t.requires_any and not (systems & t.requires_any):
            continue
        score = len(systems & t.match)
        if score > best_score:
            best, best_score = t, score
    return best


def suggestions(db: Session, organization_id: str) -> list[dict]:
    """Persisted automation opportunities that a template can take over."""
    rows = db.execute(
        select(AutomationOpportunity)
        .where(AutomationOpportunity.organization_id == organization_id)
        .order_by(AutomationOpportunity.potential_weekly_savings_seconds.desc())
    ).scalars().all()
    covered = {
        a.source_workflow
        for a in db.execute(
            select(AutomationAgent).where(AutomationAgent.organization_id == organization_id)
        ).scalars()
        if a.source_workflow
    }
    out = []
    for r in rows:
        t = suggest_template(r.workflow_name)
        if t is None:
            continue
        out.append(
            {
                "workflow_name": r.workflow_name,
                "occurrences_per_week": r.occurrences_per_week,
                "potential_weekly_savings_seconds": r.potential_weekly_savings_seconds,
                "suggested_template": t.key,
                "has_agent": r.workflow_name in covered,
            }
        )
    return out


def agent_stats(db: Session, organization_id: str) -> dict[str, dict]:
    """Per-agent run counters: runs, awaiting_approval, minutes_saved, last_run_at."""
    stats: dict[str, dict] = {}
    runs = db.execute(
        select(AgentRun).where(AgentRun.organization_id == organization_id)
    ).scalars()
    for r in runs:
        s = stats.setdefault(
            r.agent_id,
            {"runs": 0, "awaiting_approval": 0, "minutes_saved": 0, "last_run_at": None},
        )
        s["runs"] += 1
        if r.status == "awaiting_approval":
            s["awaiting_approval"] += 1
        s["minutes_saved"] += r.minutes_saved or 0
        if s["last_run_at"] is None or r.started_at > s["last_run_at"]:
            s["last_run_at"] = r.started_at
    return stats


# ── Drafts (deterministic; the AI step only rewrites them) ─────────────────────
_RUNNING = {"ACTIVE", "ENABLED", "RUNNING", "LIVE"}
_CHANNEL_PREFIX = re.compile(r"^(crm|hubspot|meta|facebook|google|linkedin)\s*[—–-]\s*", re.I)

Data = dict[str, list[CampaignRecord]]


def _running(rec: CampaignRecord) -> bool:
    return (rec.status or "").strip().upper() in _RUNNING


def _status(rec: CampaignRecord) -> str:
    return rec.status or "unknown"


def _campaign_key(name: str) -> str:
    """Name used to match one campaign across systems ("Meta — X" ≈ "X")."""
    return re.sub(r"\s+", " ", _CHANNEL_PREFIX.sub("", name)).strip().lower()


def _label(channel: str) -> str:
    return CHANNEL_LABELS.get(channel, channel)


def _draft_alignment(t: AgentTemplate, data: Data, today: str) -> str:
    crm, ads = data.get("crm", []), data.get("meta", [])
    ads_by_key = {_campaign_key(a.name): a for a in ads}
    crm_keys: set[str] = set()
    create, align, in_sync = [], [], []
    for c in crm:
        key = _campaign_key(c.name)
        crm_keys.add(key)
        a = ads_by_key.get(key)
        if a is None:
            create.append(f"  • Create a Meta Ads campaign for “{c.name}” (CRM: {_status(c)})")
        elif _running(c) != _running(a):
            align.append(f"  • Align “{a.name}”: CRM is {_status(c)}, Meta Ads is {_status(a)}")
        else:
            in_sync.append(f"  • “{a.name}” is in sync ({_status(a)})")
    orphans = [
        f"  • “{a.name}” exists in Meta Ads with no matching CRM campaign"
        for key, a in ads_by_key.items()
        if key not in crm_keys
    ]
    lines = [
        f"{t.name} — {today}",
        "",
        f"Compared {len(crm)} CRM campaigns with {len(ads)} Meta Ads campaigns.",
        "",
    ]
    for title, items in (
        ("To create", create),
        ("To align", align),
        ("Not in the CRM", orphans),
        ("In sync", in_sync),
    ):
        if items:
            lines += [f"{title}:", *items, ""]
    lines.append("Proposed changes only — nothing was changed in HubSpot or Meta Ads.")
    return "\n".join(lines)


def _draft_status_email(t: AgentTemplate, data: Data, today: str) -> str:
    records = [r for recs in data.values() for r in recs]
    running = sum(1 for r in records if _running(r))
    lines = [
        f"Subject: Campaign status — {today}",
        "",
        "Hi team,",
        "",
        f"Current status across our channels: {running} of {len(records)} campaigns are running.",
        "",
    ]
    for channel, recs in data.items():
        if recs:
            lines += [f"{_label(channel)}:", *[f"  • {r.name} — {_status(r)}" for r in recs], ""]
    stopped = [r.name for r in records if not _running(r)]
    if stopped:
        lines += ["Not running right now: " + ", ".join(stopped) + ".", ""]
    lines += ["Thanks,", "(Drafted by an automation agent. Review before sending.)"]
    return "\n".join(lines)


def _draft_report(t: AgentTemplate, data: Data, today: str) -> str:
    lines = [f"{t.name} — {today}", ""]
    total = running = 0
    for channel, recs in data.items():
        on = sum(1 for r in recs if _running(r))
        total += len(recs)
        running += on
        lines.append(f"{_label(channel)}: {len(recs)} campaigns, {on} running")
        lines += [f"  • {r.name} — {_status(r)}" for r in recs]
        lines.append("")
    lines.append(f"Total: {total} campaigns, {running} running, {total - running} not running.")
    return "\n".join(lines)


def _draft_watch(t: AgentTemplate, data: Data, today: str) -> str:
    total = sum(len(recs) for recs in data.values())
    stopped = [(ch, r) for ch, recs in data.items() for r in recs if not _running(r)]
    if not stopped:
        return f"{t.name} — {today}\n\nAll {total} campaigns are running. Nothing needs attention."
    lines = [f"{t.name} — {today}", "", f"{len(stopped)} of {total} campaigns are not running:"]
    lines += [f"  • [{_label(ch)}] {r.name} — {_status(r)}" for ch, r in stopped]
    lines += ["", "Check whether each one was paused on purpose."]
    return "\n".join(lines)


_DRAFTERS: dict[str, Callable[[AgentTemplate, Data, str], str]] = {
    "crm_ads_alignment": _draft_alignment,
    "stakeholder_update": _draft_status_email,
    "campaign_report": _draft_report,
    "campaign_watch": _draft_watch,
}

_AI_SYSTEM = (
    "You edit drafts prepared by a marketing automation agent. Rewrite the draft so "
    "it reads well for a busy marketing team. Keep every campaign name, status and "
    "number exactly as given; do not invent data, recipients or recommendations "
    "the draft does not support. Return only the rewritten draft."
)


# ── Runs ───────────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(UTC)


def _read_channel(db: Session, organization_id: str, channel: str) -> tuple[list[CampaignRecord] | None, dict]:
    name = f"Read {_label(channel)} campaigns"
    try:
        recs = integrations.fetch_campaigns(db, organization_id, channel)
    except integrations.IntegrationError as e:
        return None, {"name": name, "status": "skipped", "detail": str(e)}
    # Error text can carry request URLs (and query-string tokens): report the kind only.
    except httpx.HTTPStatusError as e:
        return None, {"name": name, "status": "failed",
                      "detail": f"{_label(channel)} API returned HTTP {e.response.status_code}"}
    except httpx.HTTPError as e:
        return None, {"name": name, "status": "failed",
                      "detail": f"Could not reach {_label(channel)} ({type(e).__name__})"}
    return recs, {"name": name, "status": "done", "detail": f"{len(recs)} campaigns"}


def run_agent(db: Session, agent: AutomationAgent, *, user_id: str | None) -> AgentRun:
    """Execute one run. The result awaits approval (or is 'failed' with no data)."""
    if agent.status != "active":
        raise AgentError("Agent is paused")
    template = get_template(agent.template)
    if template is None:
        raise AgentError(f"Unknown template '{agent.template}'")

    sandbox = get_settings().integration_mode.lower() == "sandbox"
    steps: list[dict] = []
    data: Data = {}
    for channel in template.channels:
        recs, step = _read_channel(db, agent.organization_id, channel)
        if recs is not None:
            data[channel] = recs
            if sandbox:
                step["detail"] += " (sandbox sample data)"
        steps.append(step)

    run = AgentRun(
        organization_id=agent.organization_id,
        agent_id=agent.id,
        started_by_user_id=user_id,
        sandbox=sandbox,
    )
    if not data:
        steps.append({"name": "Prepare draft", "status": "skipped",
                      "detail": "No integration data could be read."})
        run.status = "failed"
        run.provider = "none"
    else:
        draft = _DRAFTERS[template.key](template, data, _now().strftime("%Y-%m-%d"))
        steps.append({"name": "Prepare draft", "status": "done",
                      "detail": template.output_kind.replace("_", " ")})
        provider = get_provider()
        run.provider = provider.name
        if provider.name == "mock":
            steps.append({"name": "AI rewrite", "status": "skipped",
                          "detail": "No AI provider configured; the prepared draft is used as-is."})
        else:
            try:
                draft = provider.complete(system=_AI_SYSTEM, prompt=draft, max_tokens=1200) or draft
                steps.append({"name": "AI rewrite", "status": "done",
                              "detail": f"Rewritten by {provider.name}"})
            except Exception as e:  # keep the deterministic draft on any provider failure
                steps.append({"name": "AI rewrite", "status": "failed",
                              "detail": f"{type(e).__name__}; kept the prepared draft"})
        run.output = redact_text(draft)
        run.status = "awaiting_approval"

    run.steps_json = json.dumps(steps)
    run.finished_at = _now()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def review_run(
    db: Session, run: AgentRun, agent: AutomationAgent, *, approve: bool, user_id: str
) -> AgentRun:
    if run.status != "awaiting_approval":
        raise AgentError(f"Run is already {run.status}")
    run.status = "approved" if approve else "rejected"
    run.reviewed_by_user_id = user_id
    run.reviewed_at = _now()
    run.minutes_saved = agent.minutes_saved_per_run if approve else 0
    db.commit()
    db.refresh(run)
    return run
