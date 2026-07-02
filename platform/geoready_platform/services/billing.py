"""Stripe billing: hosted Checkout + webhook-driven plan changes.

Design:
- We never build a custom payment UI. ``create_checkout_session`` returns a
  hosted Stripe Checkout URL; the browser redirects there.
- The org's plan is changed only by **webhooks** (the source of truth is Stripe),
  not by the client. ``handle_event`` is a pure function over a parsed event dict
  so it is unit-testable without real Stripe or signatures.
- Keys/prices come from config (env). With no secret key, checkout raises
  ``BillingNotConfiguredError`` and the router returns a clear message.

Plan mapping:
  pro  → price = stripe_price_pro
  founding → stripe_price_founding
  business → stripe_price_business
The plan name is also stored in the Checkout Session metadata so the webhook can
set the entitlement without re-deriving it from the price.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from geoready_platform.config import get_settings
from geoready_platform.db.models import BillingAccount, Org

logger = logging.getLogger(__name__)

PAID_PLANS = ("pro", "founding", "business")


class BillingNotConfiguredError(Exception):
    pass


class UnknownPlanError(Exception):
    pass


def _price_for_plan(plan: str) -> str:
    settings = get_settings()
    mapping = {
        "pro": settings.stripe_price_pro,
        "founding": settings.stripe_price_founding,
        "business": settings.stripe_price_business,
    }
    price = mapping.get(plan)
    if not price:
        raise UnknownPlanError(f"No Stripe price configured for plan '{plan}'.")
    return price


def create_checkout_session(
    session: Session,
    *,
    org_id: str,
    plan: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
) -> str:
    """Create a hosted Stripe Checkout session and return its URL."""
    settings = get_settings()
    if not settings.billing_enabled:
        raise BillingNotConfiguredError("Billing is not configured on this server yet.")
    if plan not in PAID_PLANS:
        raise UnknownPlanError(f"'{plan}' is not a purchasable plan.")

    price = _price_for_plan(plan)

    import stripe  # imported lazily so the package isn't required unless billing is used

    stripe.api_key = settings.stripe_secret_key
    checkout = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=org_id,
        customer_email=customer_email,
        metadata={"org_id": org_id, "plan": plan},
        subscription_data={"metadata": {"org_id": org_id, "plan": plan}},
    )
    return checkout.url


def construct_event(payload: bytes, sig_header: str) -> dict:
    """Verify the webhook signature and return the parsed event dict."""
    settings = get_settings()
    import stripe

    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


def handle_event(session: Session, event: dict) -> None:
    """Apply a Stripe event to our data. Pure over the event dict — unit-testable.

    Handles the lifecycle that changes entitlements:
    - ``checkout.session.completed`` → activate the purchased plan + record IDs.
    - ``customer.subscription.deleted`` → downgrade the org to free.
    """
    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        org_id = meta.get("org_id") or obj.get("client_reference_id")
        plan = meta.get("plan")
        if not org_id or plan not in PAID_PLANS:
            logger.warning("checkout.session.completed missing org_id/plan: %s", meta)
            return
        org = session.get(Org, org_id)
        if org is None:
            logger.warning("checkout.session.completed for unknown org %s", org_id)
            return
        org.plan = plan
        _upsert_billing(
            session,
            org_id=org_id,
            customer_id=obj.get("customer"),
            subscription_id=obj.get("subscription"),
        )
        logger.info("Activated plan '%s' for org %s via Stripe", plan, org_id)

    elif etype == "customer.subscription.deleted":
        sub_id = obj.get("id")
        ba = session.execute(
            select(BillingAccount).where(BillingAccount.stripe_subscription_id == sub_id)
        ).scalar_one_or_none()
        if ba is None:
            logger.info("subscription.deleted for unknown subscription %s", sub_id)
            return
        org = session.get(Org, ba.org_id)
        if org is not None:
            org.plan = "free"
            logger.info("Downgraded org %s to free (subscription cancelled)", ba.org_id)


def _upsert_billing(session: Session, *, org_id: str, customer_id, subscription_id) -> None:
    ba = session.execute(
        select(BillingAccount).where(BillingAccount.org_id == org_id)
    ).scalar_one_or_none()
    if ba is None:
        ba = BillingAccount(org_id=org_id)
        session.add(ba)
    if customer_id:
        ba.stripe_customer_id = str(customer_id)
    if subscription_id:
        ba.stripe_subscription_id = str(subscription_id)
    session.flush()
