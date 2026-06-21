"""Core-bridge adapter unit tests — verify wrapping/serialization without network."""

from __future__ import annotations

from geoready_platform.core_bridge import audit_adapter


def test_to_jsonable_handles_dataclasses_and_nested():
    from dataclasses import dataclass

    @dataclass
    class Inner:
        a: int

    @dataclass
    class Outer:
        name: str
        inner: Inner
        items: list

    out = audit_adapter._to_jsonable(Outer(name="x", inner=Inner(a=1), items=[Inner(a=2)]))
    assert out == {"name": "x", "inner": {"a": 1}, "items": [{"a": 2}]}


def test_build_signals_maps_breakdown_categories():
    signals = audit_adapter._build_signals(
        {"robots": 18, "schema": 10},
        {"robots": {"found": True}, "schema": {"types": ["Org"]}},
    )
    by_type = {s["signal_type"]: s for s in signals}
    assert by_type["robots"]["value"]["score"] == 18
    assert by_type["robots"]["value"]["detail"] == {"found": True}
    assert all(s["source"] == "website_audit" for s in signals)


def test_run_audit_async_uses_engine(monkeypatch):
    import asyncio

    from geo_optimizer.models.results import AuditResult

    async def _fake_engine(url, project_config=None):
        return AuditResult(url=url, score=42, band="foundation", score_breakdown={"robots": 18})

    # Patch the engine entry point the adapter imports lazily.
    import geo_optimizer.core.audit as engine

    monkeypatch.setattr(engine, "run_full_audit_async", _fake_engine)

    payload = asyncio.run(audit_adapter.run_audit_async("https://x.test"))
    assert payload.score == 42
    assert payload.band == "foundation"
    assert payload.score_breakdown == {"robots": 18}
    assert any(s["signal_type"] == "robots" for s in payload.signals)
