"""Passwordless (magic-link) auth endpoints.

- ``POST /v1/auth/request`` — request a sign-in link for an email.
- ``POST /v1/auth/verify``  — exchange a link token for a session JWT.

In local dev (no email backend configured) the request endpoint returns the
sign-in link directly so the flow can be exercised end to end. In production the
link is emailed and never returned in the response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from geoready_platform.api.deps import Principal, get_db, get_principal
from geoready_platform.config import get_settings
from geoready_platform.db.models import Org, OrgMember, User
from geoready_platform.services import magic_link as ml
from geoready_platform.services.auth import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RequestLinkIn(BaseModel):
    email: EmailStr


class RequestLinkOut(BaseModel):
    sent: bool
    # Dev-only: the link/token is echoed when no email backend is configured.
    dev_login_url: str | None = None
    dev_token: str | None = None


class VerifyIn(BaseModel):
    token: str


class SessionUser(BaseModel):
    id: str
    email: str
    name: str | None = None


class SessionOrg(BaseModel):
    id: str
    name: str
    plan: str
    role: str


class VerifyOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: SessionUser
    org: SessionOrg


@router.post("/request", response_model=RequestLinkOut)
def request_link(body: RequestLinkIn, session: Session = Depends(get_db)) -> RequestLinkOut:
    settings = get_settings()
    user, raw = ml.request_magic_link(session, email=str(body.email))
    login_url = f"{settings.app_base_url}/auth/verify/?token={raw}"

    if settings.email_enabled:
        from fastapi import HTTPException, status

        from geoready_platform.services.email import EmailSendError, send_magic_link

        try:
            send_magic_link(to=user.email, login_url=login_url)
        except EmailSendError:
            # Be honest: the user is waiting for an email that won't arrive.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "We couldn't send the sign-in email right now. Please try again in a minute.",
            ) from None
        logger.info("Magic-link email dispatched to user %s", user.id)
        return RequestLinkOut(sent=True)

    if settings.auth_dev_links_enabled:
        # Local dev only: no email backend — return the link so the flow is
        # testable. NEVER enabled off-localhost (see Settings.auth_dev_links_enabled).
        logger.info("Magic-link (dev) for %s: %s", user.email, login_url)
        return RequestLinkOut(sent=True, dev_login_url=login_url, dev_token=raw)

    # No email backend AND not local: log server-side only; leak nothing.
    logger.warning("Magic-link requested but no email backend is configured; link logged for %s", user.id)
    return RequestLinkOut(sent=True)


@router.post("/verify", response_model=VerifyOut)
def verify(body: VerifyIn, session: Session = Depends(get_db)) -> VerifyOut:
    from fastapi import HTTPException, status

    try:
        user, org_id, role = ml.consume_magic_link(session, raw_token=body.token)
    except ml.InvalidMagicLinkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    org = session.get(Org, org_id)
    token = create_access_token(user_id=user.id, org_id=org_id, role=role)
    return VerifyOut(
        access_token=token,
        user=SessionUser(id=user.id, email=user.email, name=user.name),
        org=SessionOrg(id=org.id, name=org.name, plan=org.plan, role=role),
    )


class MeOut(BaseModel):
    user: SessionUser | None = None
    org: SessionOrg


@router.get("/me", response_model=MeOut)
def me(
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> MeOut:
    """Fresh user + org + plan straight from the DB.

    The frontend calls this on load and after checkout so a plan change (e.g.
    a Stripe upgrade) is reflected without forcing a re-login. The JWT still
    carries a plan-free identity; entitlements are always read live here."""
    from fastapi import HTTPException, status

    org = session.get(Org, principal.org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Org not found")

    user_out: SessionUser | None = None
    if principal.user_id:  # api-key principals have no user
        u = session.get(User, principal.user_id)
        if u is not None:
            user_out = SessionUser(id=u.id, email=u.email, name=u.name)

    return MeOut(
        user=user_out,
        org=SessionOrg(id=org.id, name=org.name, plan=org.plan, role=principal.role),
    )
