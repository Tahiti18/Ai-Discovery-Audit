"""Passwordless (magic-link) sign-in.

Flow:
1. ``request_magic_link(email)`` — find or create the user (and, for a brand-new
   user, a personal org so they immediately have a workspace), mint a single-use
   token, and return the *raw* token to the caller. The caller emails a link
   containing it. In local dev (no email configured) the API returns the link
   directly so the flow is testable end to end.
2. ``consume_magic_link(token)`` — validate the token (exists, unexpired,
   unused), mark it used, and return the user + their org so the router can issue
   a session JWT via ``create_access_token``.

Only the SHA-256 of the token is stored. Tokens are high-entropy, single-use,
and short-lived, so a fast deterministic hash is appropriate here.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from geoready_platform.db.models import MagicLinkToken, Org, OrgMember, Role, User

TOKEN_TTL_MINUTES = 15


class InvalidMagicLinkError(Exception):
    """Token is unknown, already used, or expired."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Treat a naive datetime (as SQLite returns) as UTC, so comparisons are safe."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _default_workspace_name(email: str) -> str:
    local = email.split("@", 1)[0]
    return f"{local}'s workspace"


def find_or_create_user(session: Session, *, email: str) -> tuple[User, str]:
    """Return ``(user, org_id)``. Creates the user + a personal org on first use."""
    email = _normalize_email(email)
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        membership = session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id).order_by(OrgMember.created_at.asc())
        ).scalars().first()
        if membership is not None:
            return user, membership.org_id
        # User exists but somehow has no org — give them one (defensive).
        org = Org(name=_default_workspace_name(email), plan="free")
        session.add(org)
        session.flush()
        session.add(OrgMember(org_id=org.id, user_id=user.id, role=Role.owner.value))
        session.flush()
        return user, org.id

    # Brand-new user: create user + personal org + owner membership.
    user = User(email=email)
    session.add(user)
    session.flush()
    org = Org(name=_default_workspace_name(email), plan="free")
    session.add(org)
    session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role=Role.owner.value))
    session.flush()
    return user, org.id


def request_magic_link(session: Session, *, email: str) -> tuple[User, str]:
    """Mint a single-use sign-in token. Returns ``(user, raw_token)``."""
    user, _org_id = find_or_create_user(session, email=email)
    raw = secrets.token_urlsafe(32)
    session.add(
        MagicLinkToken(
            user_id=user.id,
            token_hash=_hash(raw),
            expires_at=_utcnow() + timedelta(minutes=TOKEN_TTL_MINUTES),
        )
    )
    session.flush()
    return user, raw


def consume_magic_link(session: Session, *, raw_token: str) -> tuple[User, str, str]:
    """Validate and burn a token. Returns ``(user, org_id, role)``.

    Raises :class:`InvalidMagicLinkError` if the token is unknown, used, or
    expired.
    """
    token_hash = _hash(raw_token)
    row = session.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or _as_aware(row.expires_at) < _utcnow():
        raise InvalidMagicLinkError("This sign-in link is invalid or has expired.")

    row.used_at = _utcnow()
    user = session.get(User, row.user_id)
    if user is None:
        raise InvalidMagicLinkError("This sign-in link is invalid or has expired.")

    membership = session.execute(
        select(OrgMember).where(OrgMember.user_id == user.id).order_by(OrgMember.created_at.asc())
    ).scalars().first()
    if membership is None:
        raise InvalidMagicLinkError("No workspace is associated with this account.")

    session.flush()
    return user, membership.org_id, membership.role
