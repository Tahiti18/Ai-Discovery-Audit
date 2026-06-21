"""End-to-end Phase 0 flow: create -> verify -> audit -> signals.

The engine is stubbed at the bridge boundary so no network access occurs and
the test exercises the platform wiring, not the audit engine itself.
"""

from __future__ import annotations

import geoready_platform.services.audits as audit_svc
import geoready_platform.services.ownership as ownership
from geoready_platform.core_bridge.audit_adapter import AuditPayload


def _fake_payload(url: str) -> AuditPayload:
    return AuditPayload(
        url=url,
        score=66,
        band="good",
        score_breakdown={"robots": 18, "schema": 10},
        full_result={"url": url, "score": 66, "score_breakdown": {"robots": 18, "schema": 10}},
        signals=[
            {"source": "website_audit", "signal_type": "robots", "value": {"score": 18, "detail": None}},
            {"source": "website_audit", "signal_type": "schema", "value": {"score": 10, "detail": None}},
        ],
    )


def _verified_entity(client, headers, monkeypatch, url="https://acme.test"):
    eid = client.post(
        "/v1/entities",
        json={"canonical_name": "Acme", "website_url": url},
        headers=headers,
    ).json()["id"]
    client.post(f"/v1/entities/{eid}/verify", json={"method": "file"}, headers=headers)
    monkeypatch.setattr(ownership, "verify", lambda u, t, m: (True, None))
    client.post(f"/v1/entities/{eid}/verify/confirm", headers=headers)
    return eid


def test_audit_refused_when_unverified(client, org_key):
    eid = client.post(
        "/v1/entities",
        json={"canonical_name": "Acme", "website_url": "https://acme.test"},
        headers=org_key["headers"],
    ).json()["id"]
    resp = client.post(f"/v1/entities/{eid}/audits", headers=org_key["headers"])
    assert resp.status_code == 403
    assert "not verified" in resp.text.lower()


def test_full_audit_pipeline_writes_signals(client, org_key, monkeypatch):
    headers = org_key["headers"]
    monkeypatch.setattr(audit_svc, "run_audit", _fake_payload)
    eid = _verified_entity(client, headers, monkeypatch)

    resp = client.post(f"/v1/entities/{eid}/audits", headers=headers)
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["audit_job_id"]

    # Eager mode: the job is already complete by the time we poll.
    job = client.get(f"/v1/audits/{job_id}", headers=headers).json()
    assert job["status"] == "complete"
    assert job["score"] == 66
    assert job["band"] == "good"
    assert job["full_result"]["score"] == 66

    signals = client.get(f"/v1/entities/{eid}/signals", headers=headers).json()
    types = {s["signal_type"] for s in signals}
    assert {"robots", "schema"} <= types
    assert all(s["source"] == "website_audit" for s in signals)


def test_audit_failure_is_recorded_not_swallowed(client, org_key, monkeypatch):
    headers = org_key["headers"]

    def _boom(url):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(audit_svc, "run_audit", _boom)
    eid = _verified_entity(client, headers, monkeypatch)

    job_id = client.post(f"/v1/entities/{eid}/audits", headers=headers).json()["audit_job_id"]
    job = client.get(f"/v1/audits/{job_id}", headers=headers).json()
    assert job["status"] == "failed"
    assert "engine exploded" in job["error"]
