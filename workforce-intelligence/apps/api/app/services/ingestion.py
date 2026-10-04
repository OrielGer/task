"""Ingestion service: persist agent/extension batches with redaction & dedup.

All identity is taken from the authenticated ``Device`` — never from the
payload — so an agent cannot write data as a different employee/org.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ActivityEvent,
    BrowserEvent,
    ContentItem,
    ContentVersion,
    Device,
    Organization,
)
from app.redaction import redact_text, sanitize_url
from app.schemas import (
    ActivityEventIn,
    BrowserEventIn,
    ContentSnapshotIn,
    IngestResult,
)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_activity(db: Session, device: Device, events: list[ActivityEventIn]) -> IngestResult:
    accepted = duplicates = 0
    existing = _existing_client_ids(db, ActivityEvent, device.id)
    for e in events:
        if e.client_event_id in existing:
            duplicates += 1
            continue
        db.add(
            ActivityEvent(
                organization_id=device.organization_id,
                employee_id=device.employee_id,
                device_id=device.id,
                client_event_id=e.client_event_id,
                application=e.application[:255],
                # Defense in depth: redact anything secret-shaped in titles.
                window_title=redact_text(e.window_title)[:1024],
                started_at=e.started_at,
                ended_at=e.ended_at,
                active_seconds=max(0, e.active_seconds),
                is_idle=e.is_idle,
                is_locked=e.is_locked,
            )
        )
        existing.add(e.client_event_id)
        accepted += 1
    db.commit()
    return IngestResult(accepted=accepted, duplicates=duplicates)


def ingest_browser(db: Session, device: Device, events: list[BrowserEventIn]) -> IngestResult:
    accepted = duplicates = 0
    existing = _existing_client_ids(db, BrowserEvent, device.id)
    for e in events:
        if e.client_event_id in existing:
            duplicates += 1
            continue
        db.add(
            BrowserEvent(
                organization_id=device.organization_id,
                employee_id=device.employee_id,
                device_id=device.id,
                client_event_id=e.client_event_id,
                browser=e.browser[:50],
                domain=e.domain.lower()[:255],
                url=sanitize_url(e.url)[:2048],
                page_title=redact_text(e.page_title)[:1024],
                started_at=e.started_at,
                ended_at=e.ended_at,
                active_seconds=max(0, e.active_seconds),
                focused=e.focused,
            )
        )
        existing.add(e.client_event_id)
        accepted += 1
    db.commit()
    return IngestResult(accepted=accepted, duplicates=duplicates)


def _org_allowlist(db: Session, organization_id: str) -> set[str]:
    org = db.get(Organization, organization_id)
    if org is None or not org.allowlisted_domains:
        return set()
    return {d.strip().lower() for d in org.allowlisted_domains.split(",") if d.strip()}


def _domain_allowed(domain: str, allowlist: set[str]) -> bool:
    d = domain.lower().strip()
    if not d:
        return False
    # Exact or subdomain match against an allowlisted domain.
    return any(d == a or d.endswith("." + a) for a in allowlist)


def ingest_content(db: Session, device: Device, snaps: list[ContentSnapshotIn]) -> IngestResult:
    """Store business-text snapshots ONLY for allowlisted domains, redacted,
    with content-version dedup (no new version when the redacted text is
    unchanged)."""
    allowlist = _org_allowlist(db, device.organization_id)
    accepted = duplicates = rejected = 0

    for s in snaps:
        if not _domain_allowed(s.domain, allowlist):
            # Not an approved business domain → never store content.
            rejected += 1
            continue

        redacted = redact_text(s.content)
        chash = _content_hash(redacted)
        item = _get_or_create_item(db, device, s)

        latest = db.execute(
            select(ContentVersion)
            .where(ContentVersion.content_item_id == item.id)
            .order_by(ContentVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()

        if latest is not None and latest.content_hash == chash and not s.is_final:
            # Identical content and not a final-action snapshot → duplicate.
            duplicates += 1
            continue
        if latest is not None and latest.content_hash == chash and s.is_final and latest.is_final:
            duplicates += 1
            continue

        next_num = (latest.version_number + 1) if latest is not None else 1
        db.add(
            ContentVersion(
                organization_id=device.organization_id,
                content_item_id=item.id,
                version_number=next_num,
                content=redacted,
                content_hash=chash,
                is_final=s.is_final,
            )
        )
        accepted += 1

    db.commit()
    return IngestResult(accepted=accepted, duplicates=duplicates, rejected=rejected)


def _get_or_create_item(db: Session, device: Device, s: ContentSnapshotIn) -> ContentItem:
    sanitized_url = sanitize_url(s.url)
    # Prefer a stable external reference; otherwise key on the sanitized URL.
    ref = s.external_reference
    q = select(ContentItem).where(
        ContentItem.organization_id == device.organization_id,
        ContentItem.employee_id == device.employee_id,
        ContentItem.source == s.source,
    )
    if ref:
        q = q.where(ContentItem.external_reference == ref)
    else:
        q = q.where(ContentItem.url == sanitized_url)
    item = db.execute(q.limit(1)).scalar_one_or_none()
    if item is None:
        item = ContentItem(
            organization_id=device.organization_id,
            employee_id=device.employee_id,
            source=s.source[:50],
            domain=s.domain.lower()[:255],
            url=sanitized_url[:2048],
            content_type=s.content_type[:50],
            external_reference=ref,
        )
        db.add(item)
        db.flush()
    return item


def _existing_client_ids(db: Session, model, device_id: str) -> set[str]:
    rows = db.execute(
        select(model.client_event_id).where(model.device_id == device_id)
    ).scalars()
    return set(rows)
