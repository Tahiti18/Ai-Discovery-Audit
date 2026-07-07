"""Health, org provisioning, and auth gating."""

from __future__ import annotations


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["db"] is True


def test_create_org_returns_api_key_once(client):
    resp = client.post(
        "/v1/orgs",
        json={"name": "Org One", "owner_email": "a@b.test"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("gr_")
    assert body["org"]["plan"] == "free"


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/v1/entities").status_code == 401
    assert client.post("/v1/entities", json={}).status_code == 401


def test_invalid_api_key_rejected(client):
    resp = client.get("/v1/entities", headers={"X-API-Key": "gr_not_a_real_key"})
    assert resp.status_code == 401


def test_me_returns_fresh_org_and_plan(client, org_key):
    """The frontend reads entitlements live from /v1/auth/me (not the JWT), so a
    plan change is reflected without re-login."""
    resp = client.get("/v1/auth/me", headers=org_key["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org"]["id"] == org_key["org_id"]
    assert body["org"]["plan"] == "free"
    # API-key principals carry no user identity.
    assert body["user"] is None


def test_me_requires_auth(client):
    assert client.get("/v1/auth/me").status_code == 401
