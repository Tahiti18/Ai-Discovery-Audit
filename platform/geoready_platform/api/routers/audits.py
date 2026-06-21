"""Audit polling endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from geoready_platform.api.deps import Principal, get_db, get_principal
from geoready_platform.schemas.models import AuditOut
from geoready_platform.services import audits as audit_svc

router = APIRouter(prefix="/v1/audits", tags=["audits"])


@router.get("/{job_id}", response_model=AuditOut)
def get_audit(
    job_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> AuditOut:
    try:
        job = audit_svc.get_audit(session, org_id=principal.org_id, job_id=job_id)
    except audit_svc.AuditJobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit job not found") from None
    return AuditOut.model_validate(job)
