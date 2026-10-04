"""AI manager assistant endpoint (constrained pipeline)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.db import get_db
from app.deps import (
    AuthContext,
    assert_can_view_employee,
    get_current_user,
    load_employee_or_404,
    manager_team_or_403,
)
from app.models import TeamMember
from app.schemas import AIQueryRequest, AIQueryResponse
from app.scoping import parse_range, resolve_org, visible_employee_ids
from app.services.ai.services import ManagerAssistantService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/query", response_model=AIQueryResponse)
def ai_query(
    body: AIQueryRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIQueryResponse:
    """Answer a management question.

    Authorization happens HERE, before any retrieval: we compute the set of
    employees the asker may see and pass only that set to the pipeline. The LLM
    never receives data outside this scope and never touches the DB directly.
    """
    org = resolve_org(ctx, None)
    scope_label = "organization"

    if body.employee_id:
        emp = load_employee_or_404(db, ctx, body.employee_id)
        assert_can_view_employee(db, ctx, emp)
        employee_ids = [emp.id]
        scope_label = f"employee:{emp.display_name}"
    elif body.team_id:
        team = manager_team_or_403(db, ctx, body.team_id)
        employee_ids = list(
            db.execute(
                select(TeamMember.employee_id).where(TeamMember.team_id == team.id)
            ).scalars()
        )
        scope_label = f"team:{team.name}"
    else:
        employee_ids = visible_employee_ids(db, ctx, org)

    if not employee_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No employees in scope")

    s, e = parse_range(None, None, default_days=7)
    answer, provider = ManagerAssistantService().answer(
        db, org, employee_ids, body.question, s, e
    )
    record_audit(
        db, organization_id=org, viewer_user_id=ctx.user_id, employee_id=body.employee_id,
        action="ai_query", resource_type="ai_query",
    )
    return AIQueryResponse(answer=answer, provider=provider, used_scope=scope_label)
