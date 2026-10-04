"""Pydantic request/response schemas (mirror packages/shared-types)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    organization_id: str | None
    user_id: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    organization_id: str | None
    employee_id: str | None = None


# ── Agent ingestion ─────────────────────────────────────────────────────────
class ActivityEventIn(BaseModel):
    client_event_id: str = Field(max_length=64)
    application: str = ""
    window_title: str = ""
    started_at: datetime
    ended_at: datetime
    active_seconds: int = 0
    is_idle: bool = False
    is_locked: bool = False


class BrowserEventIn(BaseModel):
    client_event_id: str = Field(max_length=64)
    browser: str = ""
    domain: str = ""
    url: str = ""
    page_title: str = ""
    started_at: datetime
    ended_at: datetime
    active_seconds: int = 0
    focused: bool = True


class ContentSnapshotIn(BaseModel):
    client_event_id: str = Field(max_length=64)
    source: str = "other"
    domain: str = ""
    url: str = ""
    content_type: str = ""
    external_reference: str | None = None
    content: str = ""
    is_final: bool = False
    captured_at: datetime


class ActivityBatch(BaseModel):
    events: list[ActivityEventIn]


class BrowserBatch(BaseModel):
    events: list[BrowserEventIn]


class ContentBatch(BaseModel):
    events: list[ContentSnapshotIn]


class HeartbeatIn(BaseModel):
    reported_at: datetime
    agent_version: str = ""
    idle_seconds: int = 0
    is_locked: bool = False


class IngestResult(BaseModel):
    accepted: int
    duplicates: int = 0
    rejected: int = 0


class CollectorConfigOut(BaseModel):
    allowlisted_domains: list[str]
    content_debounce_seconds: int
    heartbeat_seconds: int
    batch_max: int


# ── Admin / provisioning ──────────────────────────────────────────────────────
class OrganizationCreate(BaseModel):
    name: str
    allowlisted_domains: list[str] = []


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = ""
    password: str
    role: str  # ORG_ADMIN | MANAGER | EMPLOYEE


class EmployeeCreate(BaseModel):
    display_name: str
    email: str = ""
    user_id: str | None = None


class DeviceEnrollRequest(BaseModel):
    employee_id: str
    name: str = ""


class DeviceEnrollResponse(BaseModel):
    device_id: str
    device_key: str
    device_secret: str  # shown ONCE; stored only as a hash server-side
    note: str = "Store device_secret securely; it is not retrievable again."


# ── Read models ───────────────────────────────────────────────────────────────
class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_name: str
    email: str
    status: str
    last_seen_at: datetime | None = None


class TimelineEntry(BaseModel):
    started_at: datetime
    ended_at: datetime
    kind: str
    label: str
    detail: str
    active_seconds: int


class CurrentActivity(BaseModel):
    """What an employee is working on right now (most recent focus interval)."""

    status: str  # active | idle | offline
    kind: str | None = None  # application | website
    label: str | None = None  # app name or domain
    detail: str | None = None  # window/page title
    since: datetime | None = None
    last_seen_at: datetime | None = None
    is_live: bool = False  # true if the latest event is within the live window


class UsageRow(BaseModel):
    label: str
    active_seconds: int
    event_count: int


class WorkSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    started_at: datetime
    ended_at: datetime
    active_seconds: int
    apps: str
    domains: str
    inferred_customer: str | None = None
    inferred_campaign: str | None = None
    inferred_task: str | None = None


class ContentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: str
    domain: str
    url: str
    content_type: str
    external_reference: str | None = None
    updated_at: datetime


class ContentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    content: str
    is_final: bool
    created_at: datetime


class AISummaryOut(BaseModel):
    employee_id: str
    date: str
    summary: str
    provider: str


class AIInsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    title: str
    detail: str
    recommendation: str
    severity: str


class AIQueryRequest(BaseModel):
    question: str
    employee_id: str | None = None
    team_id: str | None = None
    # For SUPER_ADMIN org-wide queries (others are pinned to their own org).
    organization_id: str | None = None


class AIQueryResponse(BaseModel):
    answer: str
    provider: str
    used_scope: str


# ── Integrations ──────────────────────────────────────────────────────────────
class IntegrationCredentialIn(BaseModel):
    channel: str  # meta | google | linkedin | crm | email
    display_name: str = ""
    token: str = ""  # secret; stored encrypted, never returned
    config: dict = {}


class IntegrationStatusOut(BaseModel):
    channel: str
    display_name: str
    configured: bool
    is_active: bool
    last_synced_at: datetime | None = None


class SyncResult(BaseModel):
    channel: str
    synced: int


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    channel: str
    external_id: str
    name: str
    status: str
    synced_at: datetime


# ── Audit ─────────────────────────────────────────────────────────────────────
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    viewer_user_id: str | None = None
    employee_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    created_at: datetime


class Page(BaseModel):
    """Generic pagination envelope."""

    items: list
    total: int
    limit: int
    offset: int
