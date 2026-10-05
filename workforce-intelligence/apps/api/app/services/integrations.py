"""Marketing-integration connectors + sync service.

Each connector reads campaigns from an external system behind the common
``MarketingIntegration`` interface. Two modes (``INTEGRATION_MODE``):

* ``sandbox`` (default) — deterministic sample data, NO network. Used for
  demos/tests and for running the whole platform offline.
* ``live`` — real HTTP calls with the per-organization decrypted token.

Credentials are stored per-organization, encrypted at rest (app.crypto). All
reads are tenant-scoped; a connector never fetches another org's data.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt
from app.models import Campaign, IntegrationCredential

CHANNELS = ("meta", "google", "linkedin", "crm", "email")


@dataclass
class CampaignRecord:
    external_id: str
    name: str
    channel: str
    status: str


class IntegrationError(RuntimeError):
    pass


class MarketingIntegration(ABC):
    channel: str = "base"

    @abstractmethod
    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        """Fetch campaigns from the real API. Implemented per provider."""

    def _sandbox_campaigns(self) -> list[CampaignRecord]:
        c = self.channel
        return [
            CampaignRecord(f"{c}-1001", f"{c.title()} — Acme Q4 Awareness", c, "ACTIVE"),
            CampaignRecord(f"{c}-1002", f"{c.title()} — Acme Retargeting", c, "PAUSED"),
        ]

    def list_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        mode = get_settings().integration_mode.lower()
        if mode == "sandbox":
            return self._sandbox_campaigns()
        if not token:
            raise IntegrationError(f"No credential configured for '{self.channel}'")
        return self._live_campaigns(token, config)


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


class MetaAdsIntegration(MarketingIntegration):
    channel = "meta"

    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        account = config.get("ad_account_id")
        if not account:
            raise IntegrationError("meta integration requires config.ad_account_id")
        with _client() as c:
            r = c.get(
                f"https://graph.facebook.com/v19.0/act_{account}/campaigns",
                params={"fields": "id,name,status", "access_token": token},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
        return [CampaignRecord(str(x.get("id")), x.get("name", ""), "meta", x.get("status", "")) for x in data]


class GoogleAdsIntegration(MarketingIntegration):
    channel = "google"

    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        # Google Ads uses a gRPC/REST API with a developer token + customer id;
        # wiring that fully is a Milestone-3 task. Sandbox mode works today.
        raise IntegrationError(
            "Google Ads live mode not yet implemented; use INTEGRATION_MODE=sandbox "
            "or implement the Google Ads API client (needs developer token + OAuth)."
        )


class LinkedInAdsIntegration(MarketingIntegration):
    channel = "linkedin"

    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        account = config.get("account_id")
        if not account:
            raise IntegrationError("linkedin integration requires config.account_id")
        with _client() as c:
            r = c.get(
                "https://api.linkedin.com/rest/adCampaigns",
                params={"q": "search", "search.account.values[0]": f"urn:li:sponsoredAccount:{account}"},
                headers={"Authorization": f"Bearer {token}", "LinkedIn-Version": "202401"},
            )
            r.raise_for_status()
            elements = r.json().get("elements", [])
        return [
            CampaignRecord(str(x.get("id")), x.get("name", ""), "linkedin", x.get("status", ""))
            for x in elements
        ]


class HubSpotIntegration(MarketingIntegration):
    channel = "crm"

    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        with _client() as c:
            r = c.get(
                "https://api.hubapi.com/marketing/v3/campaigns",
                params={"limit": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            results = r.json().get("results", [])
        out = []
        for x in results:
            props = x.get("properties", x)
            out.append(
                CampaignRecord(
                    str(x.get("id", props.get("hs_object_id", ""))),
                    props.get("hs_name", props.get("name", "")),
                    "crm",
                    props.get("hs_campaign_status", "") or "",
                )
            )
        return out


class EmailIntegration(MarketingIntegration):
    channel = "email"

    def _live_campaigns(self, token: str, config: dict) -> list[CampaignRecord]:
        # Gmail/Outlook marketing sync is a Milestone-3 task; sandbox works today.
        raise IntegrationError(
            "Email live mode not yet implemented; use INTEGRATION_MODE=sandbox."
        )


_REGISTRY: dict[str, MarketingIntegration] = {
    "meta": MetaAdsIntegration(),
    "google": GoogleAdsIntegration(),
    "linkedin": LinkedInAdsIntegration(),
    "crm": HubSpotIntegration(),
    "email": EmailIntegration(),
}


def get_integration(channel: str) -> MarketingIntegration:
    integ = _REGISTRY.get(channel)
    if integ is None:
        raise IntegrationError(f"Unknown integration channel '{channel}'")
    return integ


def _active_credential(
    db: Session, organization_id: str, channel: str
) -> IntegrationCredential | None:
    return db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.organization_id == organization_id,
            IntegrationCredential.channel == channel,
            IntegrationCredential.is_active == True,
        )
    ).scalar_one_or_none()


def _list_campaigns(
    db: Session, organization_id: str, channel: str
) -> tuple[list[CampaignRecord], IntegrationCredential | None]:
    integ = get_integration(channel)
    cred = _active_credential(db, organization_id, channel)
    token = decrypt(cred.secret_encrypted) if cred else ""
    config = json.loads(cred.config_json) if (cred and cred.config_json) else {}
    return integ.list_campaigns(token, config), cred


def fetch_campaigns(db: Session, organization_id: str, channel: str) -> list[CampaignRecord]:
    """Read one channel's campaigns without touching the local mirror.

    Read-only by design (used by automation agents). Raises IntegrationError
    in live mode when the organization has no credential for the channel.
    """
    records, _ = _list_campaigns(db, organization_id, channel)
    return records


def sync_channel(db: Session, organization_id: str, channel: str) -> int:
    """Pull campaigns for one channel into the local mirror. Returns the count.

    In sandbox mode this needs no credential; in live mode it decrypts the
    stored token for the organization.
    """
    records, cred = _list_campaigns(db, organization_id, channel)

    # Upsert into the campaigns mirror (tenant-scoped).
    existing = {
        c.external_id: c
        for c in db.execute(
            select(Campaign).where(
                Campaign.organization_id == organization_id, Campaign.channel == channel
            )
        ).scalars()
    }
    now = datetime.now(UTC)
    for rec in records:
        row = existing.get(rec.external_id)
        if row is None:
            db.add(
                Campaign(
                    organization_id=organization_id,
                    channel=channel,
                    external_id=rec.external_id,
                    name=rec.name[:512],
                    status=rec.status[:64],
                    synced_at=now,
                )
            )
        else:
            row.name = rec.name[:512]
            row.status = rec.status[:64]
            row.synced_at = now

    if cred is not None:
        cred.last_synced_at = now
    db.commit()
    return len(records)
