"""Authentication & credential primitives.

- Passwords and API keys are hashed with PBKDF2-HMAC-SHA256 (stdlib only —
  no bcrypt build dependency, which keeps Windows/CI setup frictionless).
- API keys are returned in cleartext exactly once at creation; only the hash
  and a non-secret ``prefix`` are persisted.
- JWTs are HS256 via PyJWT.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from geoready_platform.config import get_settings

_PBKDF2_ROUNDS = 240_000
_API_KEY_PREFIX = "gr_"


# ─── Password / key hashing ──────────────────────────────────────────────────


def hash_secret(secret: str) -> str:
    """Return ``pbkdf2$<rounds>$<salt_hex>$<hash_hex>``."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    try:
        scheme, rounds_s, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ─── API keys ────────────────────────────────────────────────────────────────


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(full_key, prefix, key_hash)``. ``full_key`` is shown once only."""
    body = secrets.token_urlsafe(32)
    full_key = f"{_API_KEY_PREFIX}{body}"
    prefix = full_key[:12]
    return full_key, prefix, hash_secret(full_key)


def api_key_prefix(full_key: str) -> str:
    return full_key[:12]


# ─── JWT ─────────────────────────────────────────────────────────────────────


def create_access_token(*, user_id: str, org_id: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
