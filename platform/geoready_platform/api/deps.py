"""FastAPI dependencies: DB session, authenticated principal, org scoping.

Two auth schemes are accepted:
- ``Authorization: Bearer <jwt>``  (interactive sessions)
- ``X-API-Key: gr_...``            (programmatic / CLI)

Both resolve to a :class:`Principal` carrying ``org_id`` — every downstream
service call is scoped by it, which is the application-layer half of tenant
isolation (the other half being Postgres RLS).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from geoready_platform.db.base import get_sessionmaker
from geoready_platform.db.models import ApiKey
from geoready_platform.services.auth import decode_access_token, verify_secret


@dataclass
class Principal:
    org_id: str
    user_id: str | None
    role: str
    auth_type: str  # "jwt" | "api_key"


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _principal_from_jwt(token: str) -> Principal:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing org_id")
    return Principal(org_id=org_id, user_id=payload.get("sub"), role=payload.get("role", "viewer"), auth_type="jwt")


def _principal_from_api_key(session: Session, api_key: str) -> Principal:
    prefix = api_key[:12]
    rows = session.execute(select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))).scalars().all()
    for row in rows:
        if verify_secret(api_key, row.key_hash):
            return Principal(org_id=row.org_id, user_id=None, role="editor", auth_type="api_key")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def get_principal(
    session: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    if x_api_key:
        return _principal_from_api_key(session, x_api_key)
    if authorization and authorization.lower().startswith("bearer "):
        return _principal_from_jwt(authorization.split(" ", 1)[1].strip())
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Missing credentials (provide 'Authorization: Bearer <jwt>' or 'X-API-Key')",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*allowed: str):
    """Dependency factory enforcing a minimum role set."""

    def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role in {allowed}")
        return principal

    return _checker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
