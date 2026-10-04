"""Agent / extension ingestion endpoints.

Authenticated by device credential (X-Device-Key / X-Device-Secret). Identity is
derived from the device record. These endpoints are OUTBOUND ingestion only —
there is no command/response channel back to the workstation. The only data
returned is an acknowledgement and non-executable collector config.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_authenticated_device
from app.models import Device, Employee, EmployeeStatus, Organization
from app.schemas import (
    ActivityBatch,
    BrowserBatch,
    CollectorConfigOut,
    ContentBatch,
    HeartbeatIn,
    IngestResult,
)
from app.services import ingestion

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/events/batch", response_model=IngestResult)
def ingest_events(
    batch: ActivityBatch,
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> IngestResult:
    result = ingestion.ingest_activity(db, device, batch.events)
    _touch_presence(db, device, is_locked=False)
    return result


@router.post("/browser/batch", response_model=IngestResult)
def ingest_browser(
    batch: BrowserBatch,
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> IngestResult:
    return ingestion.ingest_browser(db, device, batch.events)


@router.post("/content/batch", response_model=IngestResult)
def ingest_content(
    batch: ContentBatch,
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> IngestResult:
    # Content is stored only for allowlisted domains, after redaction (service).
    return ingestion.ingest_content(db, device, batch.events)


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatIn,
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    device.last_heartbeat_at = now
    if body.agent_version:
        device.agent_version = body.agent_version[:50]
    emp = db.get(Employee, device.employee_id)
    if emp is not None:
        emp.last_seen_at = now
        if body.is_locked:
            emp.status = EmployeeStatus.offline
        elif body.idle_seconds >= 300:
            emp.status = EmployeeStatus.idle
        else:
            emp.status = EmployeeStatus.active
    db.commit()
    return {"ok": True, "reported_at": now.isoformat()}


@router.get("/config", response_model=CollectorConfigOut)
def collector_config(
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> CollectorConfigOut:
    """Return non-executable collector configuration (allowlist + intervals).

    This is DATA, never code. Collectors apply the allowlist/intervals; they
    never execute anything received here.
    """
    settings = get_settings()
    org = db.get(Organization, device.organization_id)
    domains = []
    if org and org.allowlisted_domains:
        domains = [d.strip() for d in org.allowlisted_domains.split(",") if d.strip()]
    return CollectorConfigOut(
        allowlisted_domains=domains,
        content_debounce_seconds=settings.content_debounce_seconds,
        heartbeat_seconds=settings.heartbeat_seconds,
        batch_max=settings.batch_max,
    )


def _touch_presence(db: Session, device: Device, *, is_locked: bool) -> None:
    emp = db.get(Employee, device.employee_id)
    if emp is not None:
        emp.last_seen_at = datetime.now(UTC)
        if emp.status == EmployeeStatus.offline and not is_locked:
            emp.status = EmployeeStatus.active
        db.commit()
