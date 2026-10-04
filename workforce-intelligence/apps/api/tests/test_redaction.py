"""Secret-redaction unit tests (server-side SecretRedactor)."""
from __future__ import annotations

from app.redaction import REDACTED, SecretRedactor, redact_text


def test_authorization_header_masked():
    assert redact_text("Authorization: Bearer abcdef123456") == f"Authorization: {REDACTED}"
    assert "Basic" not in redact_text("Authorization: Basic Zm9vOmJhcg==")


def test_bearer_token_inline_masked():
    out = redact_text("call with Bearer sometoken1234567890 please")
    assert "sometoken1234567890" not in out
    assert REDACTED in out


def test_jwt_masked():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dozjgNryP4J3jVmNHl0w5N"
    assert REDACTED in redact_text(f"token {jwt} end")
    assert jwt not in redact_text(f"token {jwt} end")


def test_key_value_secrets_masked():
    assert "hunter2secret" not in redact_text("password: hunter2secret")
    assert "ABCD1234KEY99" not in redact_text("api_key = ABCD1234KEY99")
    assert "topsecretval" not in redact_text('client_secret: "topsecretval"')
    assert "123456" not in redact_text("otp: 123456")


def test_provider_api_keys_masked():
    assert redact_text("key sk-ABCDEFGHIJKLMNOP1234 here").find("sk-ABCDEFG") == -1
    assert "AKIAIOSFODNN7EXAMPLE" not in redact_text("aws AKIAIOSFODNN7EXAMPLE")


def test_private_key_block_masked():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----"
    assert redact_text(pem) == REDACTED


def test_credit_card_luhn_masked():
    out = redact_text("card 4242 4242 4242 4242 on file")
    assert "4242 4242 4242 4242" not in out
    assert REDACTED in out


def test_business_text_preserved():
    text = "Turn qualified leads into customers with AI-powered automation."
    assert redact_text(text) == text


def test_idempotent():
    text = "Authorization: Bearer abc123456789 and api_key=XYZ987LONGKEYVALUE"
    assert redact_text(redact_text(text)) == redact_text(text)


def test_configurable_extra_rule():
    import re

    from app.redaction import RedactionRule

    r = SecretRedactor(extra_rules=[RedactionRule("proj", re.compile(r"PROJ-\d+"), REDACTED)])
    assert r.redact("ticket PROJ-123") == f"ticket {REDACTED}"
