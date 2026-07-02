"""Entity service: create/list/get entities and run ownership verification.

Every query is scoped by ``org_id`` at the application layer. Combined with the
Postgres RLS policies (see the baseline migration), this gives defense in depth
for tenant isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from geoready_platform.db.models import BusinessEntity, Org
from geoready_platform.services import ownership
from geoready_platform.services.plans import PlanLimitExceededError, limits_for


class EntityNotFoundError(Exception):
    pass


class OwnershipVerificationError(Exception):
    pass


def create_entity(
    session: Session,
    *,
    org_id: str,
    canonical_name: str,
    website_url: str,
    category: str | None = None,
    geo: str | None = None,
) -> BusinessEntity:
    # Plan gate: cap the number of businesses per account.
    org = session.get(Org, org_id)
    limits = limits_for(org.plan if org else None)
    current = session.execute(
        select(func.count(BusinessEntity.id)).where(
            BusinessEntity.org_id == org_id, BusinessEntity.archived_at.is_(None)
        )
    ).scalar_one()
    if current >= limits.max_businesses:
        raise PlanLimitExceededError(
            f"Your plan includes {limits.max_businesses} "
            f"business{'es' if limits.max_businesses != 1 else ''}. "
            "Upgrade to add more.",
            upgrade_to="business",
        )

    entity = BusinessEntity(
        org_id=org_id,
        canonical_name=canonical_name,
        website_url=website_url,
        category=category,
        geo=geo,
    )
    session.add(entity)
    session.flush()
    return entity


def get_entity(session: Session, *, org_id: str, entity_id: str) -> BusinessEntity:
    stmt = select(BusinessEntity).where(
        BusinessEntity.id == entity_id,
        BusinessEntity.org_id == org_id,
        BusinessEntity.archived_at.is_(None),
    )
    entity = session.execute(stmt).scalar_one_or_none()
    if entity is None:
        raise EntityNotFoundError(entity_id)
    return entity


def list_entities(session: Session, *, org_id: str) -> list[BusinessEntity]:
    stmt = (
        select(BusinessEntity)
        .where(BusinessEntity.org_id == org_id, BusinessEntity.archived_at.is_(None))
        .order_by(BusinessEntity.created_at.desc())
    )
    return list(session.execute(stmt).scalars().all())


def start_verification(session: Session, *, org_id: str, entity_id: str, method: str) -> BusinessEntity:
    """Issue a verification token and record the chosen method (dns | file)."""
    if method not in {"dns", "file"}:
        raise OwnershipVerificationError(f"Unknown method {method!r} (expected 'dns' or 'file')")
    entity = get_entity(session, org_id=org_id, entity_id=entity_id)
    entity.verification_method = method
    entity.verification_token = ownership.generate_verification_token()
    entity.verified_at = None
    session.flush()
    return entity


def confirm_verification(session: Session, *, org_id: str, entity_id: str) -> BusinessEntity:
    """Re-check the token via the recorded method; set ``verified_at`` on success."""
    entity = get_entity(session, org_id=org_id, entity_id=entity_id)
    if not entity.verification_token or not entity.verification_method:
        raise OwnershipVerificationError("Verification has not been started for this entity")

    ok, err = ownership.verify(entity.website_url, entity.verification_token, entity.verification_method)
    if not ok:
        raise OwnershipVerificationError(err or "Verification failed")

    entity.verified_at = datetime.now(timezone.utc)
    session.flush()
    return entity
