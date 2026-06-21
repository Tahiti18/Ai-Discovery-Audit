"""Ownership verification gating."""

from __future__ import annotations

import geoready_platform.services.ownership as ownership


def _make_entity(client, headers):
    resp = client.post(
        "/v1/entities",
        json={"canonical_name": "Acme", "website_url": "https://acme.test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_start_verification_returns_token(client, org_key):
    entity_id = _make_entity(client, org_key["headers"])
    resp = client.post(
        f"/v1/entities/{entity_id}/verify",
        json={"method": "file"},
        headers=org_key["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "file"
    assert body["token"]
    assert "/.well-known/" in body["instructions"]


def test_confirm_verification_success(client, org_key, monkeypatch):
    entity_id = _make_entity(client, org_key["headers"])
    client.post(f"/v1/entities/{entity_id}/verify", json={"method": "file"}, headers=org_key["headers"])

    monkeypatch.setattr(ownership, "verify", lambda url, token, method: (True, None))
    resp = client.post(f"/v1/entities/{entity_id}/verify/confirm", headers=org_key["headers"])
    assert resp.status_code == 200
    assert resp.json()["verified"] is True


def test_confirm_verification_failure(client, org_key, monkeypatch):
    entity_id = _make_entity(client, org_key["headers"])
    client.post(f"/v1/entities/{entity_id}/verify", json={"method": "dns"}, headers=org_key["headers"])

    monkeypatch.setattr(ownership, "verify", lambda url, token, method: (False, "No record"))
    resp = client.post(f"/v1/entities/{entity_id}/verify/confirm", headers=org_key["headers"])
    assert resp.status_code == 400
    assert "No record" in resp.text
