"""Unit tests for the LLM misinformation detector.

Monkeypatches the HTTP call — exercises prompt shape, JSON parsing, validation
of issue_type / severity / confidence, sort order, and JSON serialisation.
"""

from __future__ import annotations

import pytest

from geoready_platform.services.probe import misinformation as m


# ─── prompt shape ────────────────────────────────────────────────────────────


def test_build_prompt_includes_homepage_and_answers():
    p = m.build_prompt(
        name="Era More Than Gold",
        domain="eramorethangold.com",
        website_snippet="We are the authorised dealer for Breitling, Tissot, Longines, Rado, Hamilton.",
        answers=["ERA carries Breitling, Chopard, Rado, Hamilton and Tissot."],
    )
    assert "Era More Than Gold" in p
    assert "Breitling, Tissot, Longines, Rado, Hamilton" in p  # homepage source of truth
    assert "Chopard" in p  # AI-answer content
    for issue in m._VALID_ISSUE_TYPES:
        assert issue in p


# ─── parsing + validation ───────────────────────────────────────────────────


def _valid_payload() -> str:
    return (
        '{"findings":['
        '{"issue_type":"wrong_brand","severity":"high",'
        ' "description":"AI says Era carries Chopard but the homepage does not list Chopard.",'
        ' "evidence":"ERA carries Breitling, Chopard, Rado...","fix":"Update Google Business Profile brand list.","confidence":0.95},'
        '{"issue_type":"wrong_website","severity":"high",'
        ' "description":"AI links to era-jewellers.com instead of the actual domain.",'
        ' "evidence":"Website: https://www.era-jewellers.com/","fix":"Publish canonical URL on your homepage.","confidence":0.92},'
        '{"issue_type":"wrong_location","severity":"medium",'
        ' "description":"AI calls Paphos the main store though homepage shows Limassol as flagship.",'
        ' "evidence":"main store in Paphos","fix":"Update schema to mark Limassol as the primary location.","confidence":0.8}'
        ']}'
    )


def test_parse_clean_payload_returns_findings():
    findings = m._parse_response(_valid_payload())
    assert len(findings) == 3
    assert {f.issue_type for f in findings} == {"wrong_brand", "wrong_website", "wrong_location"}


def test_parse_sorts_high_severity_first():
    findings = m._parse_response(_valid_payload())
    severities = [f.severity for f in findings]
    assert severities == ["high", "high", "medium"]


def test_parse_drops_low_confidence():
    """Confidence < 0.7 → excluded to keep the report credible."""
    payload = (
        '{"findings":['
        '{"issue_type":"wrong_brand","severity":"high",'
        ' "description":"maybe wrong","evidence":"…","fix":"…","confidence":0.55}'
        ']}'
    )
    assert m._parse_response(payload) == []


def test_parse_drops_unknown_issue_type():
    payload = (
        '{"findings":['
        '{"issue_type":"cosmic_ray","severity":"high",'
        ' "description":"desc","evidence":"e","fix":"f","confidence":0.9}'
        ']}'
    )
    assert m._parse_response(payload) == []


def test_parse_drops_invalid_severity():
    payload = (
        '{"findings":['
        '{"issue_type":"wrong_brand","severity":"catastrophic",'
        ' "description":"desc","evidence":"e","fix":"f","confidence":0.9}'
        ']}'
    )
    assert m._parse_response(payload) == []


def test_parse_drops_rows_missing_description_or_fix():
    payload = (
        '{"findings":['
        '{"issue_type":"wrong_brand","severity":"high",'
        ' "description":"","evidence":"e","fix":"f","confidence":0.9},'
        '{"issue_type":"wrong_brand","severity":"high",'
        ' "description":"d","evidence":"e","fix":"","confidence":0.9}'
        ']}'
    )
    assert m._parse_response(payload) == []


def test_parse_strips_markdown_fences():
    fenced = f"Here you go:\n```json\n{_valid_payload()}\n```"
    assert len(m._parse_response(fenced)) == 3


def test_parse_rejects_invalid_json():
    with pytest.raises(m.MisinformationError):
        m._parse_response("not json")


def test_parse_rejects_missing_findings_key():
    with pytest.raises(m.MisinformationError):
        m._parse_response('{"errors":[]}')


def test_parse_caps_at_10_findings():
    rows = ",".join(
        f'{{"issue_type":"other","severity":"low","description":"d{i}","evidence":"e","fix":"f","confidence":0.8}}'
        for i in range(15)
    )
    payload = f'{{"findings":[{rows}]}}'
    assert len(m._parse_response(payload)) == 10


# ─── storage roundtrip ──────────────────────────────────────────────────────


def test_to_json_marks_source_and_preserves_fields():
    findings = m._parse_response(_valid_payload())
    stored = m.to_json(findings)
    assert all(row["source"] == "llm_misinformation" for row in stored)
    assert all(row["issue_type"] in m._VALID_ISSUE_TYPES for row in stored)


# ─── outer function: monkeypatched HTTP ─────────────────────────────────────


def test_detect_end_to_end(monkeypatch):
    monkeypatch.setattr(m, "_post_openrouter", lambda **_: _valid_payload())
    findings = m.detect_misinformation(
        name="Era More Than Gold", domain="eramorethangold.com",
        website_snippet="We are authorised for Breitling, Tissot, Longines, Rado, Hamilton.",
        answers=["ERA carries Chopard, Breitling..."], api_key="test",
    )
    assert len(findings) == 3
    assert findings[0].severity == "high"


def test_detect_requires_snippet():
    with pytest.raises(m.MisinformationError):
        m.detect_misinformation(
            name="X", domain=None, website_snippet="",
            answers=["some answer"], api_key="k",
        )


def test_detect_requires_at_least_one_answer():
    with pytest.raises(m.MisinformationError):
        m.detect_misinformation(
            name="X", domain=None, website_snippet="homepage text",
            answers=[], api_key="k",
        )
    with pytest.raises(m.MisinformationError):
        m.detect_misinformation(
            name="X", domain=None, website_snippet="homepage text",
            answers=["", "   "], api_key="k",
        )


def test_detect_requires_api_key():
    with pytest.raises(m.MisinformationError):
        m.detect_misinformation(
            name="X", domain=None, website_snippet="text",
            answers=["a"], api_key="",
        )
