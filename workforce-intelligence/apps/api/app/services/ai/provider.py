"""AI provider abstraction.

No provider is hard-coded through the app. The provider is chosen by config
(``AI_PROVIDER``). When no API key is configured, the deterministic
``MockProvider`` is used so the whole platform runs offline.

Real providers (OpenAI/Anthropic/Gemini) are implemented as thin HTTP clients
and only activate when their key is present; otherwise the factory falls back
to the mock. ``local`` models can be added later behind the same interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import Settings, get_settings


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, *, system: str, prompt: str, max_tokens: int = 600) -> str:
        """Return a completion for the given system + user prompt."""


class MockProvider(AIProvider):
    """Deterministic, offline provider.

    It does not call any model; it produces a structured, readable answer from
    the already-aggregated context it is handed, so the MVP is fully functional
    without any API key. Output is clearly labelled as mock-generated.
    """

    name = "mock"

    def complete(self, *, system: str, prompt: str, max_tokens: int = 600) -> str:
        head = "[mock-ai] "
        # Echo a concise, deterministic synthesis of the provided context.
        lines = [ln.strip() for ln in prompt.splitlines() if ln.strip()]
        preview = " ".join(lines)[:500]
        return (
            head
            + "Based on the aggregated, tenant-scoped data provided, here is a "
            + "deterministic summary (configure an AI provider for richer output): "
            + preview
        )


class _HTTPProvider(AIProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _client(self):
        import httpx  # lazy import; only needed when a real provider is active

        return httpx.Client(timeout=30.0)


class OpenAIProvider(_HTTPProvider):
    name = "openai"

    def complete(self, *, system: str, prompt: str, max_tokens: int = 600) -> str:
        with self._client() as c:
            resp = c.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model or "gpt-4o-mini",
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"

    def complete(self, *, system: str, prompt: str, max_tokens: int = 600) -> str:
        with self._client() as c:
            resp = c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model or "claude-3-5-sonnet-latest",
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(block.get("text", "") for block in data.get("content", []))


class GeminiProvider(_HTTPProvider):
    name = "gemini"

    def complete(self, *, system: str, prompt: str, max_tokens: int = 600) -> str:
        with self._client() as c:
            model = self.model or "gemini-1.5-flash"
            resp = c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": self.api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]


def build_provider(settings: Settings | None = None) -> AIProvider:
    s = settings or get_settings()
    choice = (s.ai_provider or "mock").lower()
    if choice == "openai" and s.openai_api_key:
        return OpenAIProvider(s.openai_api_key, s.ai_model)
    if choice == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key, s.ai_model)
    if choice == "gemini" and s.gemini_api_key:
        return GeminiProvider(s.gemini_api_key, s.ai_model)
    # Default / no key configured → offline mock.
    return MockProvider()


def get_provider() -> AIProvider:
    return build_provider()
