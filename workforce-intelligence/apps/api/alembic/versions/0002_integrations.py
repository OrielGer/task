"""Integration credentials + campaigns.

Adds the ``integration_credentials`` and ``campaigns`` tables. Uses the ORM
metadata (create_all is idempotent — it only creates missing tables), keeping
the migrated schema aligned with the models.

Revision ID: 0002_integrations
Revises: 0001_initial
Create Date: 2026-10-04
"""
from __future__ import annotations

from alembic import op
from app.db import Base
from app.models import Campaign, IntegrationCredential

revision = "0002_integrations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[IntegrationCredential.__table__, Campaign.__table__],
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(
        bind=bind,
        tables=[Campaign.__table__, IntegrationCredential.__table__],
    )
