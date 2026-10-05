"""Password hashing, device-credential hashing, and JWT helpers."""
from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.config import get_settings

# pbkdf2_sha256 is a strong, pure-Python KDF (no native bcrypt version pitfalls).
# bcrypt/argon2 can be enabled here if the deployment provides those backends.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ── User passwords ────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False


# ── Device credentials ────────────────────────────────────────────────────────
# Device secrets are high-entropy random tokens; a fast salted SHA-256 is
# appropriate (unlike user passwords, which are low-entropy and use bcrypt).
def hash_device_secret(secret: str) -> str:
    settings = get_settings()
    return hashlib.sha256((settings.jwt_secret + ":" + secret).encode()).hexdigest()


def verify_device_secret(secret: str, credential_hash: str) -> bool:
    return hmac.compare_digest(hash_device_secret(secret), credential_hash)


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 of a request body, for optional agent request signing."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, body), signature)


# ── JWT ────────────────────────────────────────────────────────────────────────
def create_access_token(*, user_id: str, organization_id: str | None, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
