"""AI-based work-session classifier (optional, behind SessionClassifier).

Enabled by ``AI_SESSION_CLASSIFIER=true`` with a real provider. It always keeps
the deterministic result as a fallback and uses it verbatim when the provider
is the mock or returns unparseable output, so behavior is safe offline.
"""
from __future__ import annotations

import json

from app.config import get_settings
from app.services.ai.provider import AIProvider, MockProvider, get_provider
from app.services.work_sessions import (
    DeterministicClassifier,
    SessionClassifier,
    SessionDraft,
    system_for_domain,
)


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no json object found")
    return text[start : end + 1]


class AISessionClassifier:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_provider()
        self.fallback = DeterministicClassifier()

    def classify(self, draft: SessionDraft) -> dict[str, str | None]:
        base = self.fallback.classify(draft)
        # Mock provider can't produce structured labels → use deterministic.
        if isinstance(self.provider, MockProvider):
            return base
        systems = sorted({s for d in draft.domains if (s := system_for_domain(d))})
        prompt = (
            f"Apps: {sorted(draft.apps)}\n"
            f"Domains: {sorted(draft.domains)}\n"
            f"Systems: {systems}\n"
            f"Window/page titles: {draft.titles[:10]}\n\n"
            'Return ONLY strict JSON: {"customer": string|null, '
            '"campaign": string|null, "task": string|null}.'
        )
        try:
            raw = self.provider.complete(
                system="You label a marketing work session from the given metadata. Reply ONLY with JSON.",
                prompt=prompt,
                max_tokens=200,
            )
            obj = json.loads(_extract_json(raw))
            return {
                "inferred_customer": obj.get("customer") or base["inferred_customer"],
                "inferred_campaign": obj.get("campaign") or base["inferred_campaign"],
                "inferred_task": obj.get("task") or base["inferred_task"],
            }
        except Exception:
            return base


def get_default_classifier() -> SessionClassifier:
    if get_settings().ai_session_classifier:
        return AISessionClassifier()
    return DeterministicClassifier()
