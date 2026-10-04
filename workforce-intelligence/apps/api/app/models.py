"""SQLAlchemy models.

Every tenant-scoped table carries ``organization_id``. Primary keys are
string UUIDs for portability across Postgres (production) and SQLite (tests).
Enums are stored as VARCHAR (``native_enum=False``) so the same migration runs
on both backends.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def PK() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=_uuid)


class Role(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"


class EmployeeStatus(str, enum.Enum):
    active = "active"
    idle = "idle"
    offline = "offline"


RoleEnum = Enum(Role, native_enum=False, length=20, validate_strings=True)
StatusEnum = Enum(EmployeeStatus, native_enum=False, length=10, validate_strings=True)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = PK()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Domains on which business-text capture is permitted (comma-separated).
    allowlisted_domains: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class User(Base):
    """Login principal for the dashboard/API."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_user_org_email"),)

    id: Mapped[str] = PK()
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )  # NULL only for SUPER_ADMIN (platform-level).
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(RoleEnum, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Employee(Base):
    """A monitored person. May be linked to a login User (for EMPLOYEE self-view)."""

    __tablename__ = "employees"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), default="")
    status: Mapped[EmployeeStatus] = mapped_column(StatusEnum, default=EmployeeStatus.offline)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional manager (a User with role MANAGER).
    manager_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "employee_id", name="uq_team_member"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )


class Device(Base):
    """An enrolled, company-owned workstation. Authenticates the agent.

    The agent proves identity with ``credential_hash`` (a hashed device secret).
    The server derives employee/org from this record — an agent cannot assert a
    different employee_id. Devices can be revoked (is_active=False).
    """

    __tablename__ = "devices"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    # Public device identifier sent on every request (not a secret).
    device_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Hash of the device secret used for request authentication / HMAC.
    credential_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    agent_version: Mapped[str] = mapped_column(String(50), default="")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("device_id", "client_event_id", name="uq_activity_client_event"),
        Index("ix_activity_emp_time", "employee_id", "started_at"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    application: Mapped[str] = mapped_column(String(255), default="")
    window_title: Mapped[str] = mapped_column(String(1024), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_idle: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BrowserEvent(Base):
    __tablename__ = "browser_events"
    __table_args__ = (
        UniqueConstraint("device_id", "client_event_id", name="uq_browser_client_event"),
        Index("ix_browser_emp_time", "employee_id", "started_at"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    browser: Mapped[str] = mapped_column(String(50), default="")
    domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    url: Mapped[str] = mapped_column(String(2048), default="")  # sanitized
    page_title: Mapped[str] = mapped_column(String(1024), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    focused: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (
        Index("ix_content_item_emp", "employee_id", "source"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), default="other")
    domain: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(2048), default="")  # sanitized
    content_type: Mapped[str] = mapped_column(String(50), default="")
    external_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    versions: Mapped[list["ContentVersion"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("content_item_id", "content_hash", name="uq_version_hash"),
        Index("ix_version_item_num", "content_item_id", "version_number"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    content_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_items.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")  # already redacted
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    item: Mapped[ContentItem] = relationship(back_populates="versions")


class WorkSession(Base):
    __tablename__ = "work_sessions"
    __table_args__ = (Index("ix_session_emp_time", "employee_id", "started_at"),)

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    apps: Mapped[str] = mapped_column(Text, default="")  # comma-separated
    domains: Mapped[str] = mapped_column(Text, default="")
    inferred_customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inferred_campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inferred_task: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AISummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    summary_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    summary: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(10), default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AutomationOpportunity(Base):
    __tablename__ = "automation_opportunities"

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    workflow_name: Mapped[str] = mapped_column(String(255), default="")
    occurrences_per_week: Mapped[int] = mapped_column(Integer, default=0)
    average_seconds: Mapped[int] = mapped_column(Integer, default=0)
    employees: Mapped[str] = mapped_column(Text, default="")  # comma-separated employee ids
    estimated_weekly_seconds: Mapped[int] = mapped_column(Integer, default=0)
    automation_score: Mapped[float] = mapped_column(Float, default=0.0)
    potential_weekly_savings_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_time", "organization_id", "created_at"),)

    id: Mapped[str] = PK()
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    viewer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), default="")
    resource_type: Mapped[str] = mapped_column(String(100), default="")
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IntegrationCredential(Base):
    """Per-organization credentials for a marketing integration.

    The secret (OAuth/access token) is stored ENCRYPTED at rest via
    app.crypto; non-secret config lives in ``config_json``. One active row per
    (organization, channel).
    """

    __tablename__ = "integration_credentials"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", name="uq_integration_org_channel"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # meta|google|linkedin|crm|email
    display_name: Mapped[str] = mapped_column(String(255), default="")
    secret_encrypted: Mapped[str] = mapped_column(Text, default="")  # encrypted token
    config_json: Mapped[str] = mapped_column(Text, default="{}")  # non-secret config
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Campaign(Base):
    """A marketing campaign synced from an external system (read-only mirror)."""

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "external_id", name="uq_campaign_ext"),
        Index("ix_campaign_org_channel", "organization_id", "channel"),
    )

    id: Mapped[str] = PK()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(64), default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
