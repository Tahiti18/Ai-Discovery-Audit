"""API request/response schemas (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Orgs ────────────────────────────────────────────────────────────────────


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    owner_email: str = Field(min_length=3, max_length=320)
    owner_name: str | None = None


class OrgOut(ORMModel):
    id: str
    name: str
    plan: str
    created_at: datetime


class OrgCreated(BaseModel):
    org: OrgOut
    api_key: str = Field(description="Shown once only — store it securely.")


# ─── Entities ────────────────────────────────────────────────────────────────


class EntityCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=255)
    website_url: str = Field(min_length=4, max_length=2048)
    category: str | None = None
    geo: str | None = None


class EntityOut(ORMModel):
    id: str
    org_id: str
    canonical_name: str
    website_url: str
    category: str | None
    geo: str | None
    verified_at: datetime | None
    created_at: datetime


class VerifyStart(BaseModel):
    method: str = Field(description="'dns' or 'file'")


class VerifyStartOut(BaseModel):
    method: str
    token: str
    instructions: str


class VerifyConfirmOut(BaseModel):
    verified: bool
    verified_at: datetime | None


# ─── Signals ─────────────────────────────────────────────────────────────────


class SignalOut(ORMModel):
    id: str
    entity_id: str
    source: str
    signal_type: str
    value: dict[str, Any]
    fetched_at: datetime


# ─── Audits ──────────────────────────────────────────────────────────────────


class AuditEnqueuedOut(BaseModel):
    audit_job_id: str
    status: str


class AuditOut(ORMModel):
    id: str
    entity_id: str
    status: str
    triggered_by: str
    score: int | None
    band: str | None
    score_breakdown: dict[str, Any] | None
    full_result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
