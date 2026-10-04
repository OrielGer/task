"""Local secret redaction and URL sanitization.

This module is the privacy backbone (see SECURITY.md). It runs server-side at
ingestion as defense-in-depth; a behaviorally-aligned TypeScript port runs in
the browser extension *before* content ever leaves the workstation.

Design notes:
* We never try to be clever enough to pass secrets through "just in case".
  When in doubt we redact. Business content keeps its shape; only secret-shaped
  substrings are masked.
* Redaction is idempotent: running it twice yields the same output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

# ── Query parameters whose VALUES must never be stored ────────────────────────
SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "secret",
        "client_secret",
        "password",
        "passwd",
        "pwd",
        "auth",
        "authorization",
        "code",
        "api_key",
        "apikey",
        "key",
        "sig",
        "signature",
        "session",
        "sessionid",
        "otp",
        "mfa",
    }
)

# Substrings that make ANY param name sensitive (covers prefixed/suffixed names
# like "x_access_token" or "user_password"). "key" is deliberately NOT here to
# avoid eating innocent params like "keyword".
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "auth",
)


def _is_sensitive_param(name: str) -> bool:
    n = name.lower()
    if n in SENSITIVE_QUERY_PARAMS:
        return True
    return any(s in n for s in _SENSITIVE_SUBSTRINGS)


def sanitize_url(url: str) -> str:
    """Strip sensitive query-param values and any embedded credentials.

    Keeps the structure/visibility of the URL (scheme, host, path, param keys)
    but replaces sensitive values with ``[REDACTED]``. Userinfo (``user:pass@``)
    is removed entirely.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return REDACTED

    # Remove userinfo (credentials) from netloc, keep host[:port].
    netloc = parts.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]

    if parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        pairs = [(k, REDACTED if _is_sensitive_param(k) else v) for k, v in pairs]
        query = urlencode(pairs)
    else:
        query = parts.query

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


@dataclass
class RedactionRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


def _luhn_ok(digits: str) -> bool:
    d = [int(c) for c in digits if c.isdigit()]
    if len(d) < 13:
        return False
    total, parity = 0, len(d) % 2
    for i, n in enumerate(d):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _redact_credit_cards(text: str) -> str:
    """Mask 13–19 digit sequences (optionally space/dash grouped) passing Luhn."""

    def repl(m: re.Match[str]) -> str:
        candidate = m.group(0)
        return REDACTED if _luhn_ok(candidate) else candidate

    return re.sub(r"\b(?:\d[ -]?){13,19}\b", repl, text)


class SecretRedactor:
    """Masks secrets in free text. Configurable via extra rules."""

    def __init__(self, extra_rules: list[RedactionRule] | None = None) -> None:
        self.rules: list[RedactionRule] = _default_rules()
        if extra_rules:
            self.rules.extend(extra_rules)

    def redact(self, text: str | None) -> str:
        if not text:
            return text or ""
        out = text
        # PEM private keys first (multi-line), then line/inline rules.
        for rule in self.rules:
            out = rule.pattern.sub(rule.replacement, out)
        out = _redact_credit_cards(out)
        return out


def _default_rules() -> list[RedactionRule]:
    flags = re.IGNORECASE
    return [
        # PEM private key blocks (any type).
        RedactionRule(
            "private_key",
            re.compile(
                r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.DOTALL,
            ),
            REDACTED,
        ),
        # Authorization header (Bearer/Basic/anything) → keep key, mask value.
        RedactionRule(
            "authorization_header",
            re.compile(r"(Authorization\s*:\s*)([^\r\n]+)", flags),
            r"\1" + REDACTED,
        ),
        # Bearer tokens inline.
        RedactionRule(
            "bearer_token",
            re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", flags),
            "Bearer " + REDACTED,
        ),
        # JWTs: three base64url segments separated by dots.
        RedactionRule(
            "jwt",
            re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),
            REDACTED,
        ),
        # key: value / key = value for secret-like keys (JSON, env, headers).
        RedactionRule(
            "secret_kv",
            re.compile(
                r'(?i)\b(pass(?:word|wd)?|secret|client_secret|api[_-]?key|'
                r"access[_-]?token|refresh[_-]?token|auth[_-]?token|token|"
                r"otp|mfa|one[_-]?time[_-]?code|verification[_-]?code|private[_-]?key)"
                r'(\s*["\']?\s*[:=]\s*["\']?\s*)([^\s"\',;]{3,})',
            ),
            r"\1\2" + REDACTED,
        ),
        # Common provider API-key formats as standalone tokens.
        RedactionRule(
            "provider_api_keys",
            re.compile(
                r"\b("
                r"sk-[A-Za-z0-9]{16,}"  # OpenAI-style
                r"|AKIA[0-9A-Z]{16}"  # AWS access key id
                r"|AIza[0-9A-Za-z_-]{20,}"  # Google API key
                r"|ghp_[0-9A-Za-z]{20,}"  # GitHub PAT
                r"|xox[baprs]-[0-9A-Za-z-]{10,}"  # Slack token
                r")\b"
            ),
            REDACTED,
        ),
    ]


# Module-level singletons for convenience.
_default_redactor = SecretRedactor()


def redact_text(text: str | None) -> str:
    return _default_redactor.redact(text)
