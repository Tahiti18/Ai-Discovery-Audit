"""End-to-end probe flow with the engine/provider stubbed (no network)."""

from __future__ import annotations

import geoready_platform.services.probe.runner as runner
from geoready_platform.core_bridge.probe_adapter import ProbeResponse


def _make_entity(client, headers, *, city="Austin"):
    body = {"canonical_name": "Acme Plumbing", "website_url": "https://acme.com", "category": "plumbers"}
    if city:
        body["geo"] = city
    return client.post("/v1/entities", json=body, headers=headers).json()["id"]


def _stub_provider(monkeypatch):
    monkeypatch.setattr(runner, "resolve_probe_provider", lambda p=None: ("perplexity", "test-key"))


def _fake_run_prompt(prompt, *, provider, api_key):
    # Recommendation prompts mention the brand; one factual answer says "closed".
    if "best" in prompt.lower() or "recommend" in prompt.lower() or "hire" in prompt.lower():
        return ProbeResponse(
            prompt=prompt, provider="perplexity", model="sonar",
            text="The best option is Acme Plumbing. Globex is also notable.",
            # Includes a real competitor plus reference/review sites that must be filtered out.
            citations=["https://acme.com", "https://globex.com", "https://yelp.com/biz/x", "https://reddit.com/r/x"],
        )
    if "hours" in prompt.lower() or "services" in prompt.lower():
        return ProbeResponse(
            prompt=prompt, provider="perplexity", model="sonar",
            text="Acme Plumbing appears to be permanently closed.",
            citations=["https://acme.com"],
        )
    return ProbeResponse(
        prompt=prompt, provider="perplexity", model="sonar",
        text="Acme Plumbing is a plumbing company in Austin.",
        citations=["https://acme.com"],
    )


def test_probe_does_not_require_verification(client, org_key, monkeypatch):
    """Approved decision: probes need auth + quota only, NO ownership gate."""
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)

    eid = _make_entity(client, headers)  # never verified
    resp = client.post(f"/v1/entities/{eid}/probes", headers=headers)
    assert resp.status_code == 202, resp.text


def test_full_probe_pipeline_and_provenance(client, org_key, monkeypatch):
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)

    eid = _make_entity(client, headers)
    run_id = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]

    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] == "complete"
    assert run["provider"] == "perplexity"
    assert run["model"] == "sonar"
    assert run["taxonomy_version"]
    assert run["share_of_model"] is not None and run["share_of_model"] > 0
    assert run["prompt_count"] >= 1
    # Competitor surfaced from citations; reference/review sites filtered out.
    competitor_names = {c["name"] for c in run["competitors"]}
    assert "globex.com" in competitor_names
    assert "yelp.com" not in competitor_names
    assert "reddit.com" not in competitor_names
    # Hallucination flag surfaced at run level.
    assert any(f["type"] == "claims_closed" for f in run["flags"])

    # Per-response provenance persisted for every row.
    responses = client.get(f"/v1/probes/{run_id}/responses", headers=headers).json()
    assert responses
    for r in responses:
        assert r["provider"] == "perplexity"
        assert r["model"] == "sonar"
        assert r["taxonomy_version"]
        assert r["prompt"]
        assert r["raw_response"]
        assert r["prompt_category"]


def test_probe_quota_enforced(client, org_key, monkeypatch):
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)
    eid = _make_entity(client, headers)

    # Free tier = 3 LIFETIME checks (not per day): 4th is blocked regardless of
    # when it's attempted.
    statuses = [client.post(f"/v1/entities/{eid}/probes", headers=headers).status_code for _ in range(4)]
    assert statuses[:3] == [202, 202, 202]
    assert statuses[3] == 429
    body = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()
    assert "Founding" in body["detail"] and "$29" in body["detail"]


def test_probe_history_listed_for_entity(client, org_key, monkeypatch):
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)
    eid = _make_entity(client, headers)
    client.post(f"/v1/entities/{eid}/probes", headers=headers)

    runs = client.get(f"/v1/entities/{eid}/probes", headers=headers).json()
    assert len(runs) >= 1
    assert runs[0]["entity_id"] == eid


def test_provider_exception_marks_run_failed_not_500(client, org_key, monkeypatch):
    """A raising provider must mark the run failed, never leave it 'running' or 500."""
    headers = org_key["headers"]
    _stub_provider(monkeypatch)

    def _boom(prompt, *, provider, api_key):
        raise RuntimeError("provider SDK exploded")

    monkeypatch.setattr(runner, "run_prompt", _boom)
    eid = _make_entity(client, headers)

    resp = client.post(f"/v1/entities/{eid}/probes", headers=headers)
    assert resp.status_code == 202, resp.text
    run = client.get(f"/v1/probes/{resp.json()['probe_run_id']}", headers=headers).json()
    assert run["status"] == "failed"
    assert "exploded" in run["error"]


def test_no_provider_marks_run_failed(client, org_key, monkeypatch):
    headers = org_key["headers"]
    monkeypatch.setattr(runner, "resolve_probe_provider", lambda p=None: (None, None))
    eid = _make_entity(client, headers)
    run_id = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]
    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] == "failed"
    assert "provider" in run["error"].lower()


def test_reap_stale_runs_fails_old_active_keeps_recent_and_preserves_perceptions():
    """Stale queued/running runs (older than the threshold) are marked failed with
    a safe message; recent active runs are left alone; collected Perception rows
    are preserved."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from geoready_platform.db.base import session_scope
    from geoready_platform.db.models import AuditStatus, Perception, ProbeRun
    from geoready_platform.services.probe import runner as r

    now = r._utcnow()
    with session_scope() as s:
        stale = ProbeRun(org_id="o1", entity_id="e1", status=AuditStatus.running.value,
                         started_at=now - timedelta(minutes=20))
        queued_old = ProbeRun(org_id="o1", entity_id="e1", status=AuditStatus.queued.value,
                              started_at=now - timedelta(minutes=15))
        recent = ProbeRun(org_id="o1", entity_id="e1", status=AuditStatus.running.value,
                          started_at=now - timedelta(minutes=1))
        s.add_all([stale, queued_old, recent])
        s.flush()
        stale_id, recent_id = stale.id, recent.id
        s.add(Perception(org_id="o1", entity_id="e1", probe_run_id=stale_id,
                         prompt="q", raw_response="", prompt_category="category_recommendation"))
        s.flush()

        reaped = r.reap_stale_runs(s)
        assert reaped == 2  # stale running + old queued

        s.refresh(stale)
        s.refresh(recent)
        assert stale.status == "failed"
        assert stale.error == r.STALE_RUN_MESSAGE
        assert stale.completed_at is not None
        assert recent.status == "running"  # within threshold → untouched

        # Perceptions collected before the run stalled are preserved.
        kept = s.execute(
            select(func.count(Perception.id)).where(Perception.probe_run_id == stale_id)
        ).scalar_one()
        assert kept == 1


def test_eager_background_dispatch_does_not_block_the_post(client, org_key, monkeypatch):
    """In background-eager mode the enqueue POST must hand the job to a thread and
    return 202 WITHOUT running the probe inline — so the client gets a run id to
    poll instead of the request blocking for the whole multi-prompt probe.

    Deterministic (no real thread / no concurrent DB writes): we stub
    threading.Thread to capture the dispatch but not execute it, then assert the
    run is still pending — proving the POST did not run the probe synchronously."""
    from dataclasses import replace

    from geoready_platform.config import get_settings

    headers = org_key["headers"]
    bg_settings = replace(get_settings(), probe_eager_background=True)
    monkeypatch.setattr(runner, "get_settings", lambda: bg_settings)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)

    dispatched = {"thread": False}

    class _CapturedThread:
        def __init__(self, *a, **k):
            dispatched["thread"] = True

        def start(self):  # captured, intentionally not executed
            pass

    monkeypatch.setattr("threading.Thread", _CapturedThread)

    eid = _make_entity(client, headers)
    resp = client.post(f"/v1/entities/{eid}/probes", headers=headers)
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["probe_run_id"]

    # The POST dispatched to a background thread and returned without executing.
    assert dispatched["thread"] is True
    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] in ("queued", "running")  # not run inline → still pending


def test_all_prompts_provider_error_marks_run_failed(client, org_key, monkeypatch):
    """Every prompt 401s → run is `failed` with a safe reason, NOT a 0-visibility
    `complete` result. Per-prompt rows + details.error are preserved for diagnostics."""
    headers = org_key["headers"]
    monkeypatch.setattr(runner, "resolve_probe_provider", lambda p=None: ("openrouter", "bad-key"))

    def _all_401(prompt, *, provider, api_key):
        return ProbeResponse(
            prompt=prompt, provider="openrouter", model="perplexity/sonar", text="",
            error="HTTPStatusError: Client error '401 Unauthorized' for url 'https://openrouter.ai/...'",
        )

    monkeypatch.setattr(runner, "run_prompt", _all_401)
    eid = _make_entity(client, headers)
    run_id = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]

    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] == "failed"
    assert run["answered_count"] == 0
    assert "401" in run["error"] and "OPENROUTER_API_KEY" in run["error"]

    # Prompts are preserved as a diagnostic record with their per-prompt error.
    responses = client.get(f"/v1/probes/{run_id}/responses", headers=headers).json()
    assert responses and all(not (r["raw_response"] or "").strip() for r in responses)
    assert all(r["details"] and "401" in r["details"]["error"] for r in responses)


def test_partial_answers_stay_complete_with_warning(client, org_key, monkeypatch):
    """Some prompts succeed, some fail → run stays `complete`, answered_count < prompt_count
    so the frontend can show a partial-result warning."""
    headers = org_key["headers"]
    monkeypatch.setattr(runner, "resolve_probe_provider", lambda p=None: ("openrouter", "test-key"))

    def _partial(prompt, *, provider, api_key):
        if "best" in prompt.lower():
            return ProbeResponse(prompt=prompt, provider="openrouter", model="perplexity/sonar",
                                 text="Acme Plumbing is a great option.", citations=["https://acme.com"])
        return ProbeResponse(prompt=prompt, provider="openrouter", model="perplexity/sonar",
                             text="", error="ReadTimeout: provider timed out")

    monkeypatch.setattr(runner, "run_prompt", _partial)
    eid = _make_entity(client, headers)
    run_id = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]

    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] == "complete"
    assert 0 < run["answered_count"] < run["prompt_count"]
    assert run["error"] is None


def test_enqueue_creates_a_fresh_run_every_time(client, org_key, monkeypatch):
    """Retry path: every POST /v1/entities/{id}/probes must mint a NEW probe row
    with a distinct id — never reuse or resurrect a previous failed/complete run."""
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)
    eid = _make_entity(client, headers)

    ids = [client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]
           for _ in range(3)]
    assert len(set(ids)) == 3, f"expected three distinct run ids, got {ids}"


def test_broker_dispatch_failure_falls_back_to_thread(client, org_key, monkeypatch):
    """When .delay() raises (broker unreachable), enqueue must fall back to the
    background thread path instead of returning 500 + leaving an orphan `queued`
    row. The run must still reach a terminal status."""
    from dataclasses import replace

    from geoready_platform.config import get_settings

    headers = org_key["headers"]
    # Force the broker branch and deterministic inline thread execution.
    broker_settings = replace(get_settings(), celery_eager=False, probe_eager_background=False)
    monkeypatch.setattr(runner, "get_settings", lambda: broker_settings)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)

    # Make .delay() blow up like a missing broker would.
    import geoready_platform.workers.probe_task as probe_task
    monkeypatch.setattr(probe_task.run_probe_job, "delay",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("broker down")))

    # Run the fallback thread synchronously so the assertion below sees the
    # terminal state without sleeping/polling.
    class _SyncThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):  # noqa: ANN001
            self._target = target; self._args = args; self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr("threading.Thread", _SyncThread)

    eid = _make_entity(client, headers)
    resp = client.post(f"/v1/entities/{eid}/probes", headers=headers)
    assert resp.status_code == 202, resp.text  # NOT 500
    run = client.get(f"/v1/probes/{resp.json()['probe_run_id']}", headers=headers).json()
    assert run["status"] == "complete"  # ran via the thread fallback


def test_thread_crash_guard_marks_run_failed_not_orphaned(client, org_key, monkeypatch):
    """If the background-thread target itself raises BEFORE the probe runner can
    catch it (e.g. import error, Celery framework crash), the dispatch guard
    must mark the run failed so no row is ever stuck in `queued`."""
    from dataclasses import replace

    from geoready_platform.config import get_settings

    headers = org_key["headers"]
    bg_settings = replace(get_settings(), celery_eager=True, probe_eager_background=True)
    monkeypatch.setattr(runner, "get_settings", lambda: bg_settings)

    # Make the celery task's .apply() crash from inside the thread.
    import geoready_platform.workers.probe_task as probe_task
    monkeypatch.setattr(probe_task.run_probe_job, "apply",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("framework boom")))

    # Inline-execute the dispatched thread so the assertion sees the final state.
    class _SyncThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):  # noqa: ANN001
            self._target = target; self._args = args; self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr("threading.Thread", _SyncThread)

    eid = _make_entity(client, headers)
    resp = client.post(f"/v1/entities/{eid}/probes", headers=headers)
    assert resp.status_code == 202, resp.text
    run = client.get(f"/v1/probes/{resp.json()['probe_run_id']}", headers=headers).json()
    assert run["status"] == "failed", f"expected failed, got {run['status']}"
    assert "framework boom" in (run["error"] or "")


def test_all_answers_complete_normally(client, org_key, monkeypatch):
    """Sanity: when every prompt returns text, the run is a normal `complete`
    with answered_count == prompt_count."""
    headers = org_key["headers"]
    _stub_provider(monkeypatch)
    monkeypatch.setattr(runner, "run_prompt", _fake_run_prompt)
    eid = _make_entity(client, headers)
    run_id = client.post(f"/v1/entities/{eid}/probes", headers=headers).json()["probe_run_id"]

    run = client.get(f"/v1/probes/{run_id}", headers=headers).json()
    assert run["status"] == "complete"
    assert run["answered_count"] == run["prompt_count"] > 0
    assert run["error"] is None
