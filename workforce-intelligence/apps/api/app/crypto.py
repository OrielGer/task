"""Symmetric encryption for secrets stored at rest (integration tokens).

Uses Fernet (AES-128-CBC + HMAC). The key is derived from
``INTEGRATION_ENC_KEY`` if set, otherwise from ``JWT_SECRET`` so dev works out
of the box. In production set a dedicated ``INTEGRATION_ENC_KEY``.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    s = get_settings()
    material = (s.integration_enc_key or s.jwt_secret or "dev-key").encode()
    # Fernet needs a 32-byte urlsafe-base64 key; derive deterministically.
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        plaintext = ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
