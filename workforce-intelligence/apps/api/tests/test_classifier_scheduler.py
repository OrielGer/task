"""AI session classifier + scheduler jobs + automation persistence tests."""
from __future__ import annotations

from datetime import UTC, datetime

from app.services.ai.classifier import AISessionClassifier, get_default_classifier
from app.services.work_sessions import DeterministicClassifier, SessionDraft
from tests.conftest import auth, device_headers, provision_org


class _FakeProvider:
    name = "fake"

    def complete(self, *, system, prompt, max_tokens=600):
        return '{"customer": "Acme", "campaign": "Q4 Launch", "task": "Build Meta ads"}'


def _draft():
    d = SessionDraft(
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
    )
    d.domains = {"business.facebook.com"}
    d.apps = {"chrome.exe"}
    d.titles = ["Meta Ads Manager — Acme Q4"]
    return d


def test_classifier_mock_falls_back_to_deterministic():
    from app.services.ai.provider import MockProvider

    c = AISessionClassifier(provider=MockProvider())
    out = c.classify(_draft())
    # Mock provider → deterministic result (Meta → campaign task).
    assert out["inferred_task"] == DeterministicClassifier().classify(_draft())["inferred_task"]


def test_classifier_parses_provider_json():
    c = AISessionClassifier(provider=_FakeProvider())
    out = c.classify(_draft())
    assert out["inferred_customer"] == "Acme"
    assert out["inferred_campaign"] == "Q4 Launch"
    assert out["inferred_task"] == "Build Meta ads"


def test_classifier_bad_json_falls_back():
    class _Bad:
        name = "bad"

        def complete(self, *, system, prompt, max_tokens=600):
            return "not json at all"

    c = AISessionClassifier(provider=_Bad())
    out = c.classify(_draft())
    assert out["inferred_task"] is not None  # deterministic fallback used


def test_default_classifier_is_deterministic_by_default():
    assert isinstance(get_default_classifier(), DeterministicClassifier)


def _seed_events(client, b):
    now = datetime.now(UTC).replace(microsecond=0)
    events = [
        {"client_event_id": f"e{i}", "application": "chrome.exe", "window_title": t,
         "started_at": now.isoformat(), "ended_at": now.isoformat(),
         "active_seconds": 120, "is_idle": False, "is_locked": False}
        for i, t in enumerate(["HubSpot — Acme", "Meta Ads — Acme"])
    ]
    client.post("/api/v1/agent/events/batch", headers=device_headers(b), json={"events": events})


def test_scheduler_jobs_run(client):
    b = provision_org(client, "orgA")
    _seed_events(client, b)
    from app.services import scheduler

    # retention returns a dict of deleted counts
    assert isinstance(scheduler.job_retention(), dict)
    # nightly summaries: one per employee (2 in the fixture)
    assert scheduler.job_nightly_summaries() >= 2
    # automation recompute returns an int (>=0)
    assert isinstance(scheduler.job_automation_recompute(), int)


def test_automation_endpoint_persists_for_admin(client):
    b = provision_org(client, "orgA")
    _seed_events(client, b)
    # build some sessions first via the sessions endpoint
    client.get(f"/api/v1/employees/{b.employee_id}/sessions", headers=auth(b.admin_token))
    r = client.get("/api/v1/analytics/automation", headers=auth(b.admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)
