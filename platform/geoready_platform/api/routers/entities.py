"""Entity CRUD (minimal), ownership verification, audit enqueue, signals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from geoready_platform.api.deps import Principal, get_db, get_principal
from geoready_platform.db.models import EntitySignal
from geoready_platform.schemas.models import (
    AuditEnqueuedOut,
    EntityCreate,
    EntityOut,
    SignalOut,
    VerifyConfirmOut,
    VerifyStart,
    VerifyStartOut,
)
from geoready_platform.services import audits as audit_svc
from geoready_platform.services import entities as entity_svc
from geoready_platform.services.ownership import DNS_RECORD_PREFIX, TOKEN_PREFIX, WELL_KNOWN_PATH

router = APIRouter(prefix="/v1/entities", tags=["entities"])


@router.post("", response_model=EntityOut, status_code=201)
def create_entity(
    body: EntityCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> EntityOut:
    entity = entity_svc.create_entity(
        session,
        org_id=principal.org_id,
        canonical_name=body.canonical_name,
        website_url=body.website_url,
        category=body.category,
        geo=body.geo,
    )
    return EntityOut.model_validate(entity)


@router.get("", response_model=list[EntityOut])
def list_entities(
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[EntityOut]:
    return [EntityOut.model_validate(e) for e in entity_svc.list_entities(session, org_id=principal.org_id)]


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(
    entity_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> EntityOut:
    try:
        entity = entity_svc.get_entity(session, org_id=principal.org_id, entity_id=entity_id)
    except entity_svc.EntityNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found") from None
    return EntityOut.model_validate(entity)


@router.post("/{entity_id}/verify", response_model=VerifyStartOut)
def start_verification(
    entity_id: str,
    body: VerifyStart,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> VerifyStartOut:
    try:
        entity = entity_svc.start_verification(
            session, org_id=principal.org_id, entity_id=entity_id, method=body.method
        )
    except entity_svc.EntityNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found") from None
    except entity_svc.OwnershipVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    token = entity.verification_token or ""
    if body.method == "dns":
        instructions = f"Create a TXT record at '{DNS_RECORD_PREFIX}.<your-domain>' with value '{TOKEN_PREFIX}{token}'."
    else:
        instructions = f"Publish '{token}' at 'https://<your-domain>{WELL_KNOWN_PATH}'."
    return VerifyStartOut(method=body.method, token=token, instructions=instructions)


@router.post("/{entity_id}/verify/confirm", response_model=VerifyConfirmOut)
def confirm_verification(
    entity_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> VerifyConfirmOut:
    try:
        entity = entity_svc.confirm_verification(session, org_id=principal.org_id, entity_id=entity_id)
    except entity_svc.EntityNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found") from None
    except entity_svc.OwnershipVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return VerifyConfirmOut(verified=entity.is_verified, verified_at=entity.verified_at)


@router.post("/{entity_id}/audits", response_model=AuditEnqueuedOut, status_code=202)
def enqueue_audit(
    entity_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> AuditEnqueuedOut:
    try:
        job = audit_svc.enqueue_audit(session, org_id=principal.org_id, entity_id=entity_id)
    except entity_svc.EntityNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found") from None
    except audit_svc.EntityNotVerifiedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from None
    except audit_svc.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None
    return AuditEnqueuedOut(audit_job_id=job.id, status=job.status)


@router.get("/{entity_id}/signals", response_model=list[SignalOut])
def list_signals(
    entity_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[SignalOut]:
    # Ensure the entity belongs to the caller's org before returning signals.
    try:
        entity_svc.get_entity(session, org_id=principal.org_id, entity_id=entity_id)
    except entity_svc.EntityNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found") from None

    rows = (
        session.execute(
            select(EntitySignal)
            .where(EntitySignal.entity_id == entity_id, EntitySignal.org_id == principal.org_id)
            .order_by(EntitySignal.fetched_at.desc())
        )
        .scalars()
        .all()
    )
    return [SignalOut.model_validate(r) for r in rows]
