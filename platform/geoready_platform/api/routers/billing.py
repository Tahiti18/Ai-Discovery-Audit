"""Billing endpoints: start a Stripe Checkout, and receive Stripe webhooks.

- ``POST /v1/billing/checkout`` (authed) → returns a hosted Stripe Checkout URL.
- ``POST /v1/billing/webhook``  (Stripe-signed) → applies subscription changes.

The plan is changed only by the webhook (Stripe is the source of truth).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from geoready_platform.api.deps import Principal, get_db, get_principal
from geoready_platform.config import get_settings
from geoready_platform.db.models import Org
from geoready_platform.services import billing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan: str  # "pro" | "founding" | "business"


class CheckoutOut(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutOut)
def checkout(
    body: CheckoutIn,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> CheckoutOut:
    settings = get_settings()
    org = session.get(Org, principal.org_id)
    try:
        url = billing.create_checkout_session(
            session,
            org_id=principal.org_id,
            plan=body.plan,
            success_url=f"{settings.app_base_url}/app/?upgraded=1",
            cancel_url=f"{settings.app_base_url}/app/",
        )
    except billing.BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except billing.UnknownPlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return CheckoutOut(url=url)


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    try:
        event = billing.construct_event(payload, stripe_signature or "")
    except Exception as exc:  # noqa: BLE001 — bad signature / malformed
        logger.warning("Stripe webhook verification failed: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature") from None

    billing.handle_event(session, event)
    return {"received": True}
