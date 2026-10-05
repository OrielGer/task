"""Content-versioning tests: dedup, increments, final snapshots."""
from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import auth, device_headers, provision_org


def _content(cid: str, text: str, is_final: bool = False, ref: str = "gdoc:abc"):
    return {
        "client_event_id": cid,
        "source": "google_docs",
        "domain": "docs.google.com",
        "url": "https://docs.google.com/document/d/abc/edit",
        "content_type": "ad_copy",
        "external_reference": ref,
        "content": text,
        "is_final": is_final,
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _versions(client, b):
    items = client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token)).json()
    assert items, "expected a content item"
    item_id = items[0]["id"]
    return client.get(
        f"/api/v1/employees/{b.employee_id}/content/{item_id}/versions", headers=auth(b.admin_token)
    ).json()


def test_new_version_created_on_change(client):
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v1", "Get more customers.")]})
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v2", "Get more qualified customers.")]})
    versions = _versions(client, b)
    assert [v["version_number"] for v in versions] == [1, 2]
    assert versions[0]["content"] == "Get more customers."
    assert versions[1]["content"] == "Get more qualified customers."


def test_identical_content_deduped(client):
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v1", "Same text.")]})
    r = client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v2", "Same text.")]})
    assert r.json()["duplicates"] == 1
    versions = _versions(client, b)
    assert len(versions) == 1


def test_final_snapshot_marked(client):
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v1", "Draft text.")]})
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("v2", "Final text.", is_final=True)]})
    versions = _versions(client, b)
    assert versions[-1]["is_final"] is True


def test_separate_items_by_external_reference(client):
    b = provision_org(client, "orgA")
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("a1", "Doc A text", ref="gdoc:A")]})
    client.post("/api/v1/agent/content/batch", headers=device_headers(b), json={"events": [_content("b1", "Doc B text", ref="gdoc:B")]})
    items = client.get(f"/api/v1/employees/{b.employee_id}/content", headers=auth(b.admin_token)).json()
    assert len(items) == 2
