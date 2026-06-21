"""Tenant isolation: one org cannot read another org's entities or audits."""

from __future__ import annotations


def _new_org(client):
    import uuid

    data = client.post(
        "/v1/orgs",
        json={"name": "Org", "owner_email": f"u-{uuid.uuid4()}@x.test"},
    ).json()
    return {"X-API-Key": data["api_key"]}


def test_cross_org_entity_isolation(client):
    org_a = _new_org(client)
    org_b = _new_org(client)

    eid = client.post(
        "/v1/entities",
        json={"canonical_name": "A Corp", "website_url": "https://a.test"},
        headers=org_a,
    ).json()["id"]

    # Org B must not see or fetch Org A's entity.
    assert client.get(f"/v1/entities/{eid}", headers=org_b).status_code == 404
    assert client.get("/v1/entities", headers=org_b).json() == []
    assert client.post(f"/v1/entities/{eid}/audits", headers=org_b).status_code == 404
    assert client.get(f"/v1/entities/{eid}/signals", headers=org_b).status_code == 404
