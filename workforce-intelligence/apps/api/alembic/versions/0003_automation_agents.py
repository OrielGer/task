"""Automation agents + agent runs.

Adds the ``automation_agents`` and ``agent_runs`` tables. Uses the ORM metadata
(create_all is idempotent — it only creates missing tables), keeping the
migrated schema aligned with the models.

Revision ID: 0003_automation_agents
Revises: 0002_integrations
Create Date: 2026-10-05
"""
from __future__ import annotations

from alembic import op
from app.db import Base
from app.models import AgentRun, AutomationAgent

revision = "0003_automation_agents"
down_revision = "0002_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[AutomationAgent.__table__, AgentRun.__table__],
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(
        bind=bind,
        tables=[AgentRun.__table__, AutomationAgent.__table__],
    )
