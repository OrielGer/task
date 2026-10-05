"""Automation agents: templates, suggestions, agents, runs and their review.

Agents prepare drafts from read-only integration data; a person approves or
rejects every run (see services/automation_agents). Admins manage and run
agents; managers may view them.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import get_settings
from app.db import get_db
from app.deps import AuthContext, require_roles, require_same_org
from app.models import AgentRun, AutomationAgent, Role
from app.schemas import (
    AgentRunOut,
    AgentSuggestionOut,
    AgentTemplateOut,
    AutomationAgentCreate,
    AutomationAgentOut,
    AutomationAgentUpdate,
    AutomationTemplatesOut,
)
from app.scoping import resolve_org
from app.services import automation_agents as svc
from app.services.ai.provider import get_provider

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

_ADMINS = (Role.SUPER_ADMIN, Role.ORG_ADMIN)
_VIEWERS = (Role.SUPER_ADMIN, Role.ORG_ADMIN, Role.MANAGER)


def _load_agent(db: Session, ctx: AuthContext, agent_id: str) -> AutomationAgent:
    agent = db.get(AutomationAgent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    require_same_org(ctx, agent.organization_id)
    return agent


def _agent_out(agent: AutomationAgent, stats: dict | None) -> AutomationAgentOut:
    return AutomationAgentOut(
        id=agent.id,
        name=agent.name,
        template=agent.template,
        source_workflow=agent.source_workflow,
        status=agent.status,
        minutes_saved_per_run=agent.minutes_saved_per_run,
        created_at=agent.created_at,
        **(stats or {}),
    )


def _run_out(run: AgentRun) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
        agent_id=run.agent_id,
        status=run.status,
        steps=json.loads(run.steps_json or "[]"),
        output=run.output,
        provider=run.provider,
        sandbox=run.sandbox,
        started_at=run.started_at,
        finished_at=run.finished_at,
        reviewed_at=run.reviewed_at,
        minutes_saved=run.minutes_saved,
    )


@router.get("/templates", response_model=AutomationTemplatesOut)
def list_templates(ctx: AuthContext = Depends(require_roles(*_VIEWERS))) -> AutomationTemplatesOut:
    return AutomationTemplatesOut(
        templates=[
            AgentTemplateOut(
                key=t.key,
                name=t.name,
                description=t.description,
                channels=list(t.channels),
                output_kind=t.output_kind,
                minutes_saved_per_run=t.minutes_saved_per_run,
            )
            for t in svc.TEMPLATES
        ],
        integration_mode=get_settings().integration_mode.lower(),
        ai_provider=get_provider().name,
    )


@router.get("/suggestions", response_model=list[AgentSuggestionOut])
def list_suggestions(
    organization_id: str | None = None,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Detected repetitive workflows that a template can take over."""
    org = resolve_org(ctx, organization_id)
    return svc.suggestions(db, org)


@router.get("/agents", response_model=list[AutomationAgentOut])
def list_agents(
    organization_id: str | None = None,
    ctx: AuthContext = Depends(require_roles(*_VIEWERS)),
    db: Session = Depends(get_db),
) -> list[AutomationAgentOut]:
    org = resolve_org(ctx, organization_id)
    agents = db.execute(
        select(AutomationAgent)
        .where(AutomationAgent.organization_id == org)
        .order_by(AutomationAgent.created_at)
    ).scalars()
    stats = svc.agent_stats(db, org)
    return [_agent_out(a, stats.get(a.id)) for a in agents]


@router.post("/agents", response_model=AutomationAgentOut, status_code=201)
def create_agent(
    body: AutomationAgentCreate,
    organization_id: str | None = None,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> AutomationAgentOut:
    org = resolve_org(ctx, organization_id)
    template = svc.get_template(body.template)
    if template is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown template")
    agent = AutomationAgent(
        organization_id=org,
        name=(body.name.strip() or template.name)[:255],
        template=template.key,
        source_workflow=(body.source_workflow or "").strip() or None,
        minutes_saved_per_run=template.minutes_saved_per_run,
        created_by_user_id=ctx.user_id,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    record_audit(
        db, organization_id=org, viewer_user_id=ctx.user_id, employee_id=None,
        action="create_automation_agent", resource_type="automation_agent", resource_id=agent.id,
    )
    return _agent_out(agent, None)


@router.patch("/agents/{agent_id}", response_model=AutomationAgentOut)
def update_agent(
    agent_id: str,
    body: AutomationAgentUpdate,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> AutomationAgentOut:
    agent = _load_agent(db, ctx, agent_id)
    if body.name is not None and body.name.strip():
        agent.name = body.name.strip()[:255]
    if body.status is not None:
        agent.status = body.status
    db.commit()
    db.refresh(agent)
    record_audit(
        db, organization_id=agent.organization_id, viewer_user_id=ctx.user_id, employee_id=None,
        action="update_automation_agent", resource_type="automation_agent", resource_id=agent.id,
    )
    return _agent_out(agent, svc.agent_stats(db, agent.organization_id).get(agent.id))


@router.post("/agents/{agent_id}/run", response_model=AgentRunOut, status_code=201)
def run_agent(
    agent_id: str,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> AgentRunOut:
    agent = _load_agent(db, ctx, agent_id)
    try:
        run = svc.run_agent(db, agent, user_id=ctx.user_id)
    except svc.AgentError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    record_audit(
        db, organization_id=agent.organization_id, viewer_user_id=ctx.user_id, employee_id=None,
        action="run_automation_agent", resource_type="agent_run", resource_id=run.id,
    )
    return _run_out(run)


@router.get("/agents/{agent_id}/runs", response_model=list[AgentRunOut])
def list_runs(
    agent_id: str,
    limit: int = 20,
    ctx: AuthContext = Depends(require_roles(*_VIEWERS)),
    db: Session = Depends(get_db),
) -> list[AgentRunOut]:
    agent = _load_agent(db, ctx, agent_id)
    runs = db.execute(
        select(AgentRun)
        .where(AgentRun.agent_id == agent.id)
        .order_by(AgentRun.started_at.desc())
        .limit(max(1, min(limit, 100)))
    ).scalars()
    return [_run_out(r) for r in runs]


def _review(db: Session, ctx: AuthContext, run_id: str, *, approve: bool) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    require_same_org(ctx, run.organization_id)
    agent = db.get(AutomationAgent, run.agent_id)
    try:
        run = svc.review_run(db, run, agent, approve=approve, user_id=ctx.user_id)
    except svc.AgentError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    record_audit(
        db, organization_id=run.organization_id, viewer_user_id=ctx.user_id, employee_id=None,
        action="approve_agent_run" if approve else "reject_agent_run",
        resource_type="agent_run", resource_id=run.id,
    )
    return _run_out(run)


@router.post("/runs/{run_id}/approve", response_model=AgentRunOut)
def approve_run(
    run_id: str,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> AgentRunOut:
    return _review(db, ctx, run_id, approve=True)


@router.post("/runs/{run_id}/reject", response_model=AgentRunOut)
def reject_run(
    run_id: str,
    ctx: AuthContext = Depends(require_roles(*_ADMINS)),
    db: Session = Depends(get_db),
) -> AgentRunOut:
    return _review(db, ctx, run_id, approve=False)
