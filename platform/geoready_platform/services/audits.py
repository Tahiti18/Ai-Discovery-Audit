"""Audit service: enqueue jobs and execute them via the engine bridge.

``enqueue_audit`` enforces the ownership gate and creates a queued ``AuditJob``,
then dispatches the Celery task. ``execute_audit_job`` is the pure execution
function the worker calls; tests call it directly (no broker needed).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from geoready_platform.config import get_settings
from geoready_platform.core_bridge.audit_adapter import run_audit
from geoready_platform.db.base import session_scope
from geoready_platform.db.models import AuditJob, AuditStatus, BusinessEntity, EntitySignal, TriggeredBy
from geoready_platform.services.entities import get_entity


class EntityNotVerifiedError(Exception):
    pass


class QuotaExceededError(Exception):
    pass


class AuditJobNotFoundError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _check_quota(session: Session, org_id: str) -> None:
    settings = get_settings()
    since = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = session.execute(
        select(func.count(AuditJob.id)).where(AuditJob.org_id == org_id, AuditJob.created_at >= since)
    ).scalar_one()
    if count >= settings.free_audits_per_day:
        raise QuotaExceededError(f"Daily audit quota ({settings.free_audits_per_day}) reached")


def enqueue_audit(
    session: Session,
    *,
    org_id: str,
    entity_id: str,
    triggered_by: str = TriggeredBy.api.value,
) -> AuditJob:
    """Create a queued audit job.

    Enforces the daily quota and — when `GR_REQUIRE_OWNERSHIP_VERIFICATION=true` —
    the ownership gate. With the flag off (the default) audits run on any entity
    owned by the caller's org; the DB column, `/verify` endpoints, and ownership
    service remain in place so the gate can be re-enabled without a code change.
    """
    entity = get_entity(session, org_id=org_id, entity_id=entity_id)
    if get_settings().require_ownership_verification and not entity.is_verified:
        raise EntityNotVerifiedError("Entity ownership is not verified; audits are refused")

    _check_quota(session, org_id)

    job = AuditJob(
        entity_id=entity.id,
        org_id=org_id,
        status=AuditStatus.queued.value,
        triggered_by=triggered_by,
    )
    session.add(job)
    session.flush()
    job_id = job.id

    # The worker reads the job from a *separate* session/connection, so the job
    # must be durably committed before we dispatch — otherwise the worker (eager
    # or remote) cannot find it. Commit here makes the invariant explicit.
    session.commit()

    # Dispatch the worker. Import locally to avoid importing Celery at module load.
    from geoready_platform.workers.audit_task import run_audit_job

    settings = get_settings()
    if settings.celery_eager:
        run_audit_job.apply(args=[job_id])
    else:
        run_audit_job.delay(job_id)

    return job


def get_audit(session: Session, *, org_id: str, job_id: str) -> AuditJob:
    job = session.execute(
        select(AuditJob).where(AuditJob.id == job_id, AuditJob.org_id == org_id)
    ).scalar_one_or_none()
    if job is None:
        raise AuditJobNotFoundError(job_id)
    return job


def execute_audit_job(job_id: str) -> None:
    """Run the engine for a queued job and persist results + signals.

    Opens its own session (it runs inside a worker). Re-asserts the ownership
    gate as a defense-in-depth check, then runs the frozen engine via the
    bridge. Failures are recorded on the job, never swallowed silently.
    """
    with session_scope() as session:
        job = session.get(AuditJob, job_id)
        if job is None:
            raise AuditJobNotFoundError(job_id)
        entity = session.get(BusinessEntity, job.entity_id)
        if entity is None:
            job.status = AuditStatus.failed.value
            job.error = "Entity missing at execution time"
            job.completed_at = _utcnow()
            return
        if get_settings().require_ownership_verification and not entity.is_verified:
            job.status = AuditStatus.failed.value
            job.error = "Entity ownership not verified at execution time"
            job.completed_at = _utcnow()
            return

        job.status = AuditStatus.running.value
        job.started_at = _utcnow()
        session.flush()

        url = entity.website_url
        org_id = entity.org_id
        entity_id = entity.id

    # Run the (potentially slow) audit OUTSIDE the DB transaction.
    try:
        payload = run_audit(url)
    except Exception as exc:  # noqa: BLE001 — record any engine/timeout failure
        with session_scope() as session:
            job = session.get(AuditJob, job_id)
            if job is not None:
                job.status = AuditStatus.failed.value
                job.error = f"{type(exc).__name__}: {exc}"
                job.completed_at = _utcnow()
        return

    with session_scope() as session:
        job = session.get(AuditJob, job_id)
        if job is None:
            raise AuditJobNotFoundError(job_id)
        job.status = AuditStatus.complete.value
        job.score = payload.score
        job.band = payload.band
        job.score_breakdown = payload.score_breakdown
        job.full_result = payload.full_result
        job.completed_at = _utcnow()

        for sig in payload.signals:
            session.add(
                EntitySignal(
                    entity_id=entity_id,
                    org_id=org_id,
                    source=sig["source"],
                    signal_type=sig["signal_type"],
                    value=sig["value"],
                )
            )
