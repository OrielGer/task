"""Audit logging helper.

Every access to detailed employee content/data should create an audit record
(see SECURITY.md §6).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    organization_id: str | None,
    viewer_user_id: str | None,
    employee_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    commit: bool = True,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            viewer_user_id=viewer_user_id,
            employee_id=employee_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    )
    if commit:
        db.commit()
