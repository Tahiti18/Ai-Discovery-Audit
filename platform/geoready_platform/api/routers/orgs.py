"""Org provisioning. Creating an org bootstraps an owner user + an API key.

The API key is returned exactly once in the response and never again.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from geoready_platform.api.deps import get_db
from geoready_platform.db.models import ApiKey, Org, OrgMember, Role, User
from geoready_platform.schemas.models import OrgCreate, OrgCreated, OrgOut
from geoready_platform.services.auth import generate_api_key

router = APIRouter(prefix="/v1/orgs", tags=["orgs"])


@router.post("", response_model=OrgCreated, status_code=201)
def create_org(body: OrgCreate, session: Session = Depends(get_db)) -> OrgCreated:
    org = Org(name=body.name)
    session.add(org)
    session.flush()

    user = User(email=body.owner_email, name=body.owner_name)
    session.add(user)
    session.flush()

    session.add(OrgMember(org_id=org.id, user_id=user.id, role=Role.owner.value))

    full_key, prefix, key_hash = generate_api_key()
    session.add(ApiKey(org_id=org.id, name="default", prefix=prefix, key_hash=key_hash))
    session.flush()

    return OrgCreated(org=OrgOut.model_validate(org), api_key=full_key)
