"""Liveness / readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from geoready_platform.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(session: Session = Depends(get_db)) -> dict:
    db_ok = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
