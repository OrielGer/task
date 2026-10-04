"""Event/content ingestion tests, including privacy guarantees and device auth."""
from __future__ import annotations

from datetime import datetime, timezone

from tests.conftest import auth, device_headers, provision_org


def _activity(cid: str, title: str = "HubSpot — Acme"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "client_event_id": cid,
        "application": "chrome.exe",
        "window_title": title,
        "started_at": now,
        "ended_at": now,
        "active_seconds": 120,
        "is_idle": False,
        "is_locked": False,
    }


def test_device_can_ingest_activity(client):
    b = provision_org(client, "orgA")
    r = client.post(
        "/api/v1/agent/events/batch",
        headers=device_headers(b),
        json={"events": [_activity("e1"), _activity("e2")]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2


def test_duplicate_events_deduped(client):
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": [_activity("dup")]})
    r = client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": [_activity("dup")]})
    assert r.json()["accepted"] == 0
    assert r.json()["duplicates"] == 1


def test_missing_device_credentials_rejected(client):
    provision_org(client, "orgA")
    r = client.post("/api/v1/agent/events/batch", json={"events": [_activity("e1")]})
    assert r.status_code == 401


def test_wrong_device_secret_rejected(client):
    b = provision_org(client, "orgA")
    r = client.post(
        "/api/v1/agent/events/batch",
        headers={"X-Device-Key": b.device_key, "X-Device-Secret": "wrong"},
        json={"events": [_activity("e1")]},
    )
    assert r.status_code == 401


def test_revoked_device_rejected(client):
    b = provision_org(client, "orgA")
    rev = client.post(f"/api/v1/devices/{b.device_id}/revoke", headers=auth(b.admin_token))
    assert rev.status_code == 200
    r = client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": [_activity("e1")]})
    assert r.status_code == 401


def test_identity_is_derived_from_device_not_payload(client):
    """An agent cannot attribute data to a different employee: the payload has
    no employee field, and ingested events are tied to the device's employee."""
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": [_activity("e1")]})
    # The events must show up for the device's own employee...
    r = client.get(f"/api/v1/employees/{b.employee_id}/timeline", headers=auth(b.admin_token))
    assert any(x["label"] == "chrome.exe" for x in r.json())
    # ...and NOT for the other employee.
    r2 = client.get(f"/api/v1/employees/{b.other_employee_id}/timeline", headers=auth(b.admin_token))
    assert r2.json() == []


def test_window_title_secrets_are_redacted_on_ingest(client):
    b = provision_org(client, "orgA")
    client.post(
        "/api/v1/agent/events/batch",
        headers=device_headers(b),
        json={"events": [_activity("sek", title="login Authorization: Bearer abcdef123456")]},
    )
    r = client.get(f"/api/v1/employees/{b.employee_id}/timeline", headers=auth(b.admin_token))
    titles = " ".join(x["detail"] for x in r.json())
    assert "abcdef123456" not in titles
    assert "[REDACTED]" in titles


def test_content_only_stored_for_allowlisted_domains(client):
    b = provision_org(client, "orgA")
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "events": [
            {  # allowlisted → stored
                "client_event_id": "c1", "source": "google_docs", "domain": "docs.google.com",
                "url": "https://docs.google.com/document/d/x/edit", "content_type": "ad_copy",
                "content": "Headline v1", "is_final": False, "captured_at": now,
            },
            {  # NOT allowlisted → rejected
                "client_event_id": "c2", "source": "other", "domain": "random-personal-site.example",
                "url": "https://random-personal-site.example/", "content_type": "note",
                "content": "private stuff", "is_final": False, "captured_at": now,
            },
        ]
    }
    r = client.post("/api/v1/agent/content/batch", headers=device_headers(b), json=payload)
    assert r.json()["accepted"] == 1
    assert r.json()["rejected"] == 1

    items = client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token)).json()
    domains = {i["domain"] for i in items}
    assert "docs.google.com" in domains
    assert "random-personal-site.example" not in domains


def test_password_content_is_redacted_before_storage(client):
    """Even if a secret is typed into an allowlisted editor, it is redacted."""
    b = provision_org(client, "orgA")
    now = datetime.now(timezone.utc).isoformat()
    secret_text = "draft with password: SuperSecret123 and api_key=ABCDEF1234567890"
    client.post(
        "/api/v1/agent/content/batch",
        headers=device_headers(b),
        json={"events": [{
            "client_event_id": "cpw", "source": "google_docs", "domain": "docs.google.com",
            "url": "https://docs.google.com/document/d/x/edit", "content_type": "doc",
            "content": secret_text, "is_final": True, "captured_at": now,
        }]},
    )
    items = client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token)).json()
    item_id = items[0]["id"]
    versions = client.get(
        f"/api/v1/employees/{b.employee_id}/content/{item_id}/versions", headers=auth(b.admin_token)
    ).json()
    stored = versions[-1]["content"]
    assert "SuperSecret123" not in stored
    assert "ABCDEF1234567890" not in stored
    assert "[REDACTED]" in stored
