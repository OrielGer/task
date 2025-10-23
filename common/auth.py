"""
Authentication Utilities
Common authentication utility functions for C2 system
"""

import hashlib
import secrets


def generate_token():
    """
    Generate secure random token

    Returns:
        str: 64-character hex token (32 bytes)
    """
    return secrets.token_hex(32)


def hash_token(token):
    """
    Hash token for safe logging (don't log raw tokens)

    Args:
        token: Token to hash

    Returns:
        str: First 8 chars of SHA256 hash
    """
    if not token:
        return "NONE"

    return hashlib.sha256(token.encode()).hexdigest()[:8]
