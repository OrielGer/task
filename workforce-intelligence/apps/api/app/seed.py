"""Seed demo data (idempotent).

Creates one organization with an ORG_ADMIN, a MANAGER, and an EMPLOYEE, two
employees on a team, an enrolled device, and a day of sample activity/browser
events plus versioned business content — enough for the dashboard to render and
the AI summary/recommendations to produce output with the mock provider.

Run: ``python -m app.seed``. Change/remove before any real deployment.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    ActivityEvent,
    BrowserEvent,
    ContentItem,
    ContentVersion,
    Device,
    Employee,
    EmployeeStatus,
    Organization,
    Role,
    Team,
    TeamMember,
    User,
)
from app.security import hash_device_secret, hash_password
from app.services.work_sessions import build_sessions

DEMO_ORG = "Acme Marketing"
DEMO_DEVICE_KEY = "dev_demo_daniel"
DEMO_DEVICE_SECRET = "demo-device-secret-change-me"


def _cid() -> str:
    return uuid.uuid4().hex[:32]


def seed() -> None:
    db = SessionLocal()
    try:
        if db.execute(select(Organization).where(Organization.name == DEMO_ORG)).scalar_one_or_none():
            print("[seed] demo org already present; skipping.")
            return

        org = Organization(
            name=DEMO_ORG,
            allowlisted_domains="docs.google.com,business.facebook.com,app.hubspot.com",
        )
        db.add(org)
        db.flush()

        admin = User(
            organization_id=org.id, email="admin@acme.example", full_name="Avery Admin",
            password_hash=hash_password("Passw0rd!admin"), role=Role.ORG_ADMIN,
        )
        manager = User(
            organization_id=org.id, email="manager@acme.example", full_name="Morgan Manager",
            password_hash=hash_password("Passw0rd!mgr"), role=Role.MANAGER,
        )
        daniel_user = User(
            organization_id=org.id, email="daniel@acme.example", full_name="Daniel Employee",
            password_hash=hash_password("Passw0rd!emp"), role=Role.EMPLOYEE,
        )
        db.add_all([admin, manager, daniel_user])
        db.flush()

        daniel = Employee(
            organization_id=org.id, user_id=daniel_user.id, display_name="Daniel Employee",
            email="daniel@acme.example", status=EmployeeStatus.active,
            last_seen_at=datetime.now(UTC),
        )
        maya = Employee(
            organization_id=org.id, display_name="Maya Marketer", email="maya@acme.example",
            status=EmployeeStatus.idle,
        )
        db.add_all([daniel, maya])
        db.flush()

        team = Team(organization_id=org.id, name="Growth", manager_user_id=manager.id)
        db.add(team)
        db.flush()
        db.add_all([
            TeamMember(organization_id=org.id, team_id=team.id, employee_id=daniel.id),
            TeamMember(organization_id=org.id, team_id=team.id, employee_id=maya.id),
        ])

        device = Device(
            organization_id=org.id, employee_id=daniel.id, name="Daniel-Workstation",
            device_key=DEMO_DEVICE_KEY, credential_hash=hash_device_secret(DEMO_DEVICE_SECRET),
            is_active=True, agent_version="0.1.0", last_heartbeat_at=datetime.now(UTC),
        )
        maya_device = Device(
            organization_id=org.id, employee_id=maya.id, name="Maya-Workstation",
            device_key="dev_demo_maya", credential_hash=hash_device_secret("demo-maya-secret"),
            is_active=True, agent_version="0.1.0", last_heartbeat_at=datetime.now(UTC),
        )
        db.add_all([device, maya_device])
        db.flush()

        # Seed the last 5 days with a recurring CRM → Docs → Ads pattern so the
        # repetitive-workflow detector and automation recommendations have input.
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        for day_offset in range(5):
            day = today - timedelta(days=day_offset)
            _seed_day(db, org.id, daniel.id, device.id, day, with_content=(day_offset == 0))
        # A lighter two days for Maya so team analytics show two contributors.
        for day_offset in range(2):
            day = today - timedelta(days=day_offset)
            _seed_day(db, org.id, maya.id, maya_device.id, day, with_content=False)
        db.commit()

        # Build sessions for each seeded day so timeline/sessions/workflows populate.
        for emp in (daniel, maya):
            for day_offset in range(5):
                day = today - timedelta(days=day_offset)
                build_sessions(db, org.id, emp.id, day, day + timedelta(days=1))

        # Populate the campaigns mirror (sandbox mode needs no credentials).
        try:
            from app.services.integrations import sync_channel

            for channel in ("meta", "crm"):
                sync_channel(db, org.id, channel)
        except Exception as exc:  # non-fatal for the demo
            print(f"[seed] campaign sync skipped: {exc}")

        print("[seed] demo data created.")
        print("[seed] ORG_ADMIN  admin@acme.example / Passw0rd!admin")
        print("[seed] MANAGER    manager@acme.example / Passw0rd!mgr")
        print("[seed] EMPLOYEE   daniel@acme.example / Passw0rd!emp")
        print(f"[seed] DEVICE     key={DEMO_DEVICE_KEY} secret={DEMO_DEVICE_SECRET}")
    finally:
        db.close()


def _seed_day(db, org_id: str, emp_id: str, device_id: str, day: datetime, with_content: bool = True) -> None:
    base = day.replace(hour=9, minute=0, second=0, microsecond=0)

    # Activity (application focus) intervals.
    acts = [
        ("chrome.exe", "HubSpot — Acme customer record", 0, 7 * 60),
        ("chrome.exe", "Acme corporate website", 11 * 60, 7 * 60),
        ("chrome.exe", "ChatGPT — ad copy brainstorm", 18 * 60, 13 * 60),
        ("chrome.exe", "Google Docs — Acme Q4 campaign brief", 31 * 60, 17 * 60),
        ("chrome.exe", "Meta Ads Manager — Acme Q4 campaign", 48 * 60, 22 * 60),
    ]
    for app_name, title, offset, dur in acts:
        start = base + timedelta(seconds=offset)
        db.add(ActivityEvent(
            organization_id=org_id, employee_id=emp_id, device_id=device_id,
            client_event_id=_cid(), application=app_name, window_title=title,
            started_at=start, ended_at=start + timedelta(seconds=dur), active_seconds=dur,
        ))

    # Browser (active tab) intervals on the same timeline.
    sites = [
        ("app.hubspot.com", "https://app.hubspot.com/contacts/acme", "HubSpot — Acme", 0, 7 * 60),
        ("acme-customer.example", "https://acme-customer.example/", "Acme corporate website", 11 * 60, 7 * 60),
        ("chat.openai.com", "https://chat.openai.com/", "ChatGPT", 18 * 60, 13 * 60),
        ("docs.google.com", "https://docs.google.com/document/d/abc123/edit", "Acme Q4 campaign brief", 31 * 60, 17 * 60),
        ("business.facebook.com", "https://business.facebook.com/adsmanager", "Meta Ads Manager", 48 * 60, 22 * 60),
    ]
    for domain, url, title, offset, dur in sites:
        start = base + timedelta(seconds=offset)
        db.add(BrowserEvent(
            organization_id=org_id, employee_id=emp_id, device_id=device_id,
            client_event_id=_cid(), browser="chrome", domain=domain, url=url, page_title=title,
            started_at=start, ended_at=start + timedelta(seconds=dur), active_seconds=dur, focused=True,
        ))

    if not with_content:
        return

    # Versioned business content captured on an allowlisted domain (Google Docs).
    item = ContentItem(
        organization_id=org_id, employee_id=emp_id, source="google_docs",
        domain="docs.google.com", url="https://docs.google.com/document/d/abc123/edit",
        content_type="ad_copy", external_reference="gdoc:abc123",
    )
    db.add(item)
    db.flush()
    versions = [
        "Get more customers with our platform.",
        "Get more qualified customers using our AI platform.",
        "Turn qualified leads into customers with AI-powered automation.",
    ]
    import hashlib
    for i, text in enumerate(versions, start=1):
        db.add(ContentVersion(
            organization_id=org_id, content_item_id=item.id, version_number=i,
            content=text, content_hash=hashlib.sha256(text.encode()).hexdigest(),
            is_final=(i == len(versions)),
            created_at=base + timedelta(seconds=31 * 60 + i * 120),
        ))


def main() -> None:
    seed()


if __name__ == "__main__":
    main()
