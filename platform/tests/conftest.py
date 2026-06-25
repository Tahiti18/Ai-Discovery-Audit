"""Test fixtures. Configures an isolated SQLite DB and eager Celery BEFORE any
platform module is imported (settings/engine are cached on first use).
"""

from __future__ import annotations

import os
import tempfile

# ── Configure environment before importing the app/config (cached settings) ──
_TMP_DB = os.path.join(tempfile.gettempdir(), "geoready_platform_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["GR_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["GR_CELERY_EAGER"] = "true"
os.environ["GR_PROBE_EAGER_BACKGROUND"] = "false"  # deterministic inline completion in tests
os.environ["GR_JWT_SECRET"] = "test-secret"
os.environ["GR_FREE_AUDITS_PER_DAY"] = "5"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from geoready_platform.api.main import create_app  # noqa: E402
from geoready_platform.db.base import get_engine  # noqa: E402
from geoready_platform.db.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def org_key(client: TestClient) -> dict:
    """Create an org and return {'org_id', 'api_key', 'headers'}."""
    import uuid

    resp = client.post(
        "/v1/orgs",
        json={"name": "Acme Agency", "owner_email": f"owner-{uuid.uuid4()}@acme.test", "owner_name": "Owner"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    api_key = data["api_key"]
    return {
        "org_id": data["org"]["id"],
        "api_key": api_key,
        "headers": {"X-API-Key": api_key},
    }
