"""Subscription plans and the limits each one grants.

Single source of truth for tier gating. The backend already counts businesses
(entities) and probe runs, so enforcement is just comparing against these
limits. Prices live in Stripe; this module only models entitlements.

Tiers (see the pricing memo):
- free     — the hook: 1 business, a few checks, report viewable, no technical
             download or history.
- founding — the $29/mo lifetime price for the first ~100 customers; same
             entitlements as pro.
- pro      — $39/mo: 1 business, unlimited checks, history, technical report.
- business — ~$99/mo: up to 5 businesses, everything in pro.
- agency   — later: many businesses + white-label.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    max_businesses: int
    checks_per_day: int | None   # None = unlimited per day
    checks_total: int | None     # None = no lifetime cap; free is capped forever
    technical_report: bool        # downloadable dev audit
    history: bool                 # trends over time


# Free is a complete taste, not a free tier of daily service: 3 checks TOTAL
# (baseline + one recheck + a spare), then a hard upgrade wall. A daily
# allowance would let a motivated freeloader run a whole consulting practice on
# our API budget. Paid plans have no lifetime cap.
PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(max_businesses=1, checks_per_day=None, checks_total=3, technical_report=False, history=False),
    "founding": PlanLimits(max_businesses=1, checks_per_day=None, checks_total=None, technical_report=True, history=True),
    "pro": PlanLimits(max_businesses=1, checks_per_day=None, checks_total=None, technical_report=True, history=True),
    "business": PlanLimits(max_businesses=5, checks_per_day=None, checks_total=None, technical_report=True, history=True),
    "agency": PlanLimits(max_businesses=100, checks_per_day=None, checks_total=None, technical_report=True, history=True),
    # Internal comped tier for the product owner / staff (GR_COMPED_EMAILS):
    # effectively unlimited so any business can be tested. Never sold.
    "owner": PlanLimits(max_businesses=10_000, checks_per_day=None, checks_total=None, technical_report=True, history=True),
}


def is_gated(plan: str | None) -> bool:
    """True when paid-only report content (fix text, full ranking rows) must be
    redacted for this plan. Keyed off ``technical_report`` so the single free
    tier is gated and every paid/owner tier is not — no plan-name string checks
    scattered across the codebase."""
    return not limits_for(plan).technical_report


class PlanLimitExceededError(Exception):
    """Raised when an action would exceed the org's plan limits. Carries a
    user-facing message and the plan that would be needed."""

    def __init__(self, message: str, *, upgrade_to: str = "pro") -> None:
        super().__init__(message)
        self.upgrade_to = upgrade_to


def limits_for(plan: str | None) -> PlanLimits:
    """Return the limits for a plan, defaulting to free for anything unknown."""
    return PLAN_LIMITS.get((plan or "free").lower(), PLAN_LIMITS["free"])
