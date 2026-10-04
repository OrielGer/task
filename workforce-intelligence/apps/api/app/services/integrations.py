"""Marketing-integration interfaces.

Design-only for Milestone 1 (per spec): the interfaces are defined so live
connectors can be added later without touching callers. Concrete
implementations (OAuth, API clients) land in Milestone 2.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CampaignRecord:
    external_id: str
    name: str
    channel: str  # meta | google | linkedin | email | crm
    status: str
    updated_at: datetime | None = None


class MarketingIntegration(ABC):
    """A read connector to an external marketing system.

    Implementations must be tenant-scoped and must never fetch another
    organization's data. Credentials are stored per-organization.
    """

    channel: str = "base"

    @abstractmethod
    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:
        ...


class MetaAdsIntegration(MarketingIntegration):
    channel = "meta"

    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:  # pragma: no cover - stub
        raise NotImplementedError("Meta Ads integration arrives in Milestone 2.")


class GoogleAdsIntegration(MarketingIntegration):
    channel = "google"

    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:  # pragma: no cover - stub
        raise NotImplementedError("Google Ads integration arrives in Milestone 2.")


class LinkedInAdsIntegration(MarketingIntegration):
    channel = "linkedin"

    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:  # pragma: no cover - stub
        raise NotImplementedError("LinkedIn Ads integration arrives in Milestone 2.")


class HubSpotIntegration(MarketingIntegration):
    channel = "crm"

    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:  # pragma: no cover - stub
        raise NotImplementedError("HubSpot integration arrives in Milestone 2.")


class EmailIntegration(MarketingIntegration):
    """Gmail/Outlook connector (metadata + approved content only)."""

    channel = "email"

    def list_campaigns(self, organization_id: str) -> list[CampaignRecord]:  # pragma: no cover - stub
        raise NotImplementedError("Email integration arrives in Milestone 2.")
