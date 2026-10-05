"""URL-sanitization unit tests."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from app.redaction import REDACTED, sanitize_url

SENSITIVE = [
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "auth",
    "authorization",
    "code",
    "api_key",
    "key",
]


def test_each_sensitive_param_value_removed():
    for p in SENSITIVE:
        url = f"https://example.com/path?{p}=supersecretvalue&keep=yes"
        out = sanitize_url(url)
        assert "supersecretvalue" not in out, p
        q = parse_qs(urlsplit(out).query)
        assert q.get(p) == [REDACTED], p
        assert q.get("keep") == ["yes"], p


def test_safe_params_preserved():
    out = sanitize_url("https://example.com/s?q=marketing+plan&page=3&sort=asc")
    q = parse_qs(urlsplit(out).query)
    assert q["q"] == ["marketing plan"]
    assert q["page"] == ["3"]
    assert q["sort"] == ["asc"]


def test_prefixed_param_names_detected():
    out = sanitize_url("https://x.com/?x_access_token=abc&user_password=pw&keyword=ok")
    assert "abc" not in out
    assert "pw" not in out
    assert "keyword=ok" in out  # 'key' substring must NOT trigger on 'keyword'


def test_userinfo_credentials_removed():
    out = sanitize_url("https://user:pass@example.com/p?x=1")
    assert "user:pass" not in out
    assert "example.com" in out


def test_url_without_query_is_structurally_unchanged():
    out = sanitize_url("https://docs.google.com/document/d/abc123/edit")
    assert out == "https://docs.google.com/document/d/abc123/edit"


def test_fragment_and_path_preserved():
    out = sanitize_url("https://example.com/a/b?token=zzz#section")
    assert out.endswith("#section")
    assert "zzz" not in out


def test_empty_url():
    assert sanitize_url("") == ""
