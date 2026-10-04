"""Marketing-integration configuration, sync, and campaign read endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.crypto import encrypt
from app.db import get_db
from app.deps import AuthContext, get_current_user, require_roles
from app.models import Campaign, IntegrationCredential, Role
from app.schemas import (
    CampaignOut,
    IntegrationCredentialIn,
    IntegrationStatusOut,
    SyncResult,
)
from app.scoping import resolve_org
from app.services import integrations

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatusOut])
def list_integrations(
    organization_id: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IntegrationStatusOut]:
    org = resolve_org(ctx, organization_id)
    creds = {
        c.channel: c
        for c in db.execute(
            select(IntegrationCredential).where(IntegrationCredential.organization_id == org)
        ).scalars()
    }
    out = []
    for channel in integrations.CHANNELS:
        c = creds.get(channel)
        out.append(
            IntegrationStatusOut(
                channel=channel,
                display_name=c.display_name if c else "",
                configured=c is not None,
                is_active=c.is_active if c else False,
                last_synced_at=c.last_synced_at if c else None,
            )
        )
    return out


@router.put("/{organization_id}/credentials", response_model=IntegrationStatusOut)
def set_credential(
    organization_id: str,
    body: IntegrationCredentialIn,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationStatusOut:
    resolve_org(ctx, organization_id)
    if body.channel not in integrations.CHANNELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown channel")
    cred = db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.organization_id == organization_id,
            IntegrationCredential.channel == body.channel,
        )
    ).scalar_one_or_none()
    if cred is None:
        cred = IntegrationCredential(organization_id=organization_id, channel=body.channel)
        db.add(cred)
    cred.display_name = body.display_name[:255]
    cred.config_json = json.dumps(body.config or {})
    if body.token:
        cred.secret_encrypted = encrypt(body.token)  # never stored in plaintext
    cred.is_active = True
    db.commit()
    db.refresh(cred)
    record_audit(
        db, organization_id=organization_id, viewer_user_id=ctx.user_id, employee_id=None,
        action="set_integration_credential", resource_type="integration", resource_id=body.channel,
    )
    return IntegrationStatusOut(
        channel=cred.channel, display_name=cred.display_name, configured=True,
        is_active=cred.is_active, last_synced_at=cred.last_synced_at,
    )


@router.post("/{organization_id}/{channel}/sync", response_model=SyncResult)
def sync(
    organization_id: str,
    channel: str,
    ctx: AuthContext = Depends(require_roles(Role.SUPER_ADMIN, Role.ORG_ADMIN)),
    db: Session = Depends(get_db),
) -> SyncResult:
    resolve_org(ctx, organization_id)
    if channel not in integrations.CHANNELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown channel")
    try:
        n = integrations.sync_channel(db, organization_id, channel)
    except integrations.IntegrationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    record_audit(
        db, organization_id=organization_id, viewer_user_id=ctx.user_id, employee_id=None,
        action="sync_integration", resource_type="integration", resource_id=channel,
    )
    return SyncResult(channel=channel, synced=n)


@router.get("/{organization_id}/campaigns", response_model=list[CampaignOut])
def list_campaigns(
    organization_id: str,
    channel: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Campaign]:
    resolve_org(ctx, organization_id)
    q = select(Campaign).where(Campaign.organization_id == organization_id)
    if channel:
        q = q.where(Campaign.channel == channel)
    return list(db.execute(q.order_by(Campaign.synced_at.desc())).scalars())
