"""Billing: plan changes are driven by webhook events (Stripe is the truth).

These tests exercise the pure ``handle_event`` over synthetic Stripe event dicts
— no real Stripe, no network, no signatures — proving the entitlement logic
before real keys exist.
"""

from __future__ import annotations

from sqlalchemy import select

from geoready_platform.db.base import session_scope
from geoready_platform.db.models import BillingAccount, Org
from geoready_platform.services import billing


def _new_org(plan: str = "free") -> str:
    with session_scope() as s:
        org = Org(name="Acme", plan=plan)
        s.add(org)
        s.flush()
        return org.id


def test_checkout_completed_activates_plan_and_records_ids():
    org_id = _new_org("free")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"org_id": org_id, "plan": "founding"},
            "client_reference_id": org_id,
            "customer": "cus_123",
            "subscription": "sub_123",
        }},
    }
    with session_scope() as s:
        billing.handle_event(s, event)

    with session_scope() as s:
        org = s.get(Org, org_id)
        assert org.plan == "founding"
        ba = s.execute(select(BillingAccount).where(BillingAccount.org_id == org_id)).scalar_one()
        assert ba.stripe_customer_id == "cus_123"
        assert ba.stripe_subscription_id == "sub_123"


def test_subscription_deleted_downgrades_to_free():
    org_id = _new_org("pro")
    with session_scope() as s:
        s.add(BillingAccount(org_id=org_id, stripe_customer_id="cus_x", stripe_subscription_id="sub_x"))

    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_x"}},
    }
    with session_scope() as s:
        billing.handle_event(s, event)

    with session_scope() as s:
        assert s.get(Org, org_id).plan == "free"


def test_unknown_or_irrelevant_event_is_ignored():
    org_id = _new_org("free")
    # An event we don't act on must not change anything or raise.
    billing_event = {"type": "invoice.paid", "data": {"object": {}}}
    with session_scope() as s:
        billing.handle_event(s, billing_event)
    with session_scope() as s:
        assert s.get(Org, org_id).plan == "free"


def test_checkout_completed_missing_plan_is_ignored():
    org_id = _new_org("free")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"org_id": org_id}}},  # no plan
    }
    with session_scope() as s:
        billing.handle_event(s, event)
    with session_scope() as s:
        assert s.get(Org, org_id).plan == "free"  # unchanged
