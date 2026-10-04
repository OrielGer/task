"""Marketing-integration tests: sandbox sync, encryption-at-rest, live path."""
from __future__ import annotations

import httpx

from app.crypto import decrypt, encrypt
from tests.conftest import auth, provision_org


def test_crypto_roundtrip():
    enc = encrypt("super-secret-token")
    assert enc != "super-secret-token"
    assert decrypt(enc) == "super-secret-token"


def test_list_integrations(client):
    b = provision_org(client, "orgA")
    r = client.get("/api/v1/integrations", headers=auth(b.admin_token))
    assert r.status_code == 200
    channels = {i["channel"] for i in r.json()}
    assert {"meta", "google", "linkedin", "crm", "email"} <= channels


def test_set_credential_encrypts_token(client):
    b = provision_org(client, "orgA")
    r = client.put(
        f"/api/v1/integrations/{b.org_id}/credentials",
        headers=auth(b.admin_token),
        json={"channel": "meta", "display_name": "Acme Meta", "token": "plain-token-123", "config": {"ad_account_id": "1"}},
    )
    assert r.status_code == 200
    # Stored ciphertext must not contain the plaintext token.
    from app.db import SessionLocal
    from app.models import IntegrationCredential
    from sqlalchemy import select

    db = SessionLocal()
    try:
        cred = db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.organization_id == b.org_id,
                IntegrationCredential.channel == "meta",
            )
        ).scalar_one()
        assert "plain-token-123" not in cred.secret_encrypted
        assert decrypt(cred.secret_encrypted) == "plain-token-123"
    finally:
        db.close()


def test_sandbox_sync_and_campaigns(client):
    b = provision_org(client, "orgA")
    r = client.post(f"/api/v1/integrations/{b.org_id}/meta/sync", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert r.json()["synced"] == 2
    camps = client.get(f"/api/v1/integrations/{b.org_id}/campaigns", headers=auth(b.admin_token)).json()
    assert len(camps) == 2
    assert all(c["channel"] == "meta" for c in camps)


def test_sync_is_idempotent(client):
    b = provision_org(client, "orgA")
    client.post(f"/api/v1/integrations/{b.org_id}/meta/sync", headers=auth(b.admin_token))
    client.post(f"/api/v1/integrations/{b.org_id}/meta/sync", headers=auth(b.admin_token))
    camps = client.get(f"/api/v1/integrations/{b.org_id}/campaigns", headers=auth(b.admin_token)).json()
    assert len(camps) == 2  # upsert, not duplicate


def test_employee_cannot_configure_credential(client):
    b = provision_org(client, "orgA")
    r = client.put(
        f"/api/v1/integrations/{b.org_id}/credentials",
        headers=auth(b.employee_token),
        json={"channel": "meta", "token": "x"},
    )
    assert r.status_code == 403


def test_cannot_sync_other_org(client):
    a = provision_org(client, "orgA")
    other = provision_org(client, "orgB")
    r = client.post(f"/api/v1/integrations/{other.org_id}/meta/sync", headers=auth(a.admin_token))
    assert r.status_code == 404


def test_meta_live_path_mocked(monkeypatch):
    """The live connector parses the real API shape (no network, mocked)."""
    import app.services.integrations as I

    class _S:
        integration_mode = "live"

    monkeypatch.setattr(I, "get_settings", lambda: _S)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "act_123/campaigns" in str(request.url)
        return httpx.Response(200, json={"data": [
            {"id": "c1", "name": "Live Campaign", "status": "ACTIVE"},
        ]})

    monkeypatch.setattr(I, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    recs = I.MetaAdsIntegration().list_campaigns("token", {"ad_account_id": "123"})
    assert len(recs) == 1
    assert recs[0].name == "Live Campaign"
    assert recs[0].channel == "meta"
