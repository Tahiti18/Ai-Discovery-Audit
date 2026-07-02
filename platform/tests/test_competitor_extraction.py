"""Unit tests for the LLM-based competitor classifier.

The HTTP call itself is monkeypatched — these tests exercise prompt shape,
JSON parsing (with fences and without), dedupe, confidence gating, and the
report-shape filter. Integration is separately covered by the probe-runner
tests using a stub classifier.
"""

from __future__ import annotations

import pytest

from geoready_platform.services.probe import competitor_extraction as ce


# ─── prompt shape ────────────────────────────────────────────────────────────


def test_build_prompt_includes_entity_facts_and_all_answers():
    p = ce.build_prompt(
        name="Era More Than Gold", category="jewellery", city="Limassol",
        domain="eramorethangold.com",
        answers=[("Q1", "A1"), ("Q2", "A2")],
        candidate_domains=["lefkarasilver.com", "michalisdiamond.com"],
    )
    assert "Era More Than Gold" in p
    assert "jewellery" in p and "Limassol" in p and "eramorethangold.com" in p
    assert "Q1" in p and "A1" in p and "Q2" in p and "A2" in p
    assert "lefkarasilver.com" in p and "michalisdiamond.com" in p
    # The buyer-intent framing is what makes this work — assert it survives.
    assert "buyer" in p.lower() and "instead" in p.lower()


def test_build_prompt_survives_missing_fields():
    p = ce.build_prompt(
        name="Acme", category=None, city=None, domain=None,
        answers=[], candidate_domains=[],
    )
    assert "Acme" in p
    # No crash on empty inputs.


# ─── JSON parsing ────────────────────────────────────────────────────────────


def _valid_payload() -> str:
    return (
        '{"competitors":['
        '{"name":"Michalis Diamond Gallery","domain":"michalisdiamond.com","mentions":4,'
        '"type":"business","confidence":0.95,"why":"luxury jeweller in Limassol"},'
        '{"name":"Panos Melekkis","domain":"panosmelekkis.com","mentions":4,'
        '"type":"business","confidence":0.9,"why":"bespoke jewellery"},'
        '{"name":"Lefkara Silver","domain":"lefkarasilver.com","mentions":3,'
        '"type":"adjacent","confidence":0.85,"why":"tourist silver — different buyer intent"},'
        '{"name":"The Cyprus Guide","domain":"thecyguide.com","mentions":2,'
        '"type":"directory","confidence":0.95,"why":"tourism directory"}'
        ']}'
    )


def test_parse_clean_json():
    items = ce._parse_response(_valid_payload())
    assert len(items) == 4
    business = [c for c in items if c.type == "business"]
    assert {c.name for c in business} == {"Michalis Diamond Gallery", "Panos Melekkis"}
    assert all(0 <= c.confidence <= 1 for c in items)


def test_parse_strips_markdown_fences():
    fenced = f"Here you go:\n```json\n{_valid_payload()}\n```\n"
    items = ce._parse_response(fenced)
    assert len(items) == 4


def test_parse_rejects_invalid_json():
    with pytest.raises(ce.CompetitorExtractionError):
        ce._parse_response("not json at all")


def test_parse_rejects_missing_competitors_key():
    with pytest.raises(ce.CompetitorExtractionError):
        ce._parse_response('{"results": []}')


def test_parse_skips_rows_missing_a_name():
    items = ce._parse_response(
        '{"competitors":[{"mentions":1,"type":"business","confidence":0.9},'
        '{"name":"OK","mentions":1,"type":"business","confidence":0.9}]}'
    )
    assert [c.name for c in items] == ["OK"]


def test_parse_clamps_confidence():
    items = ce._parse_response(
        '{"competitors":[{"name":"X","mentions":1,"type":"business","confidence":5}]}'
    )
    assert items[0].confidence == 1.0


# ─── dedupe ──────────────────────────────────────────────────────────────────


def test_dedupe_folds_variants_by_domain():
    a = ce.ClassifiedCompetitor("ABC Jewellery", "abc.com", 2, "business", 0.9)
    b = ce.ClassifiedCompetitor("ABC Jewellery Ltd", "abc.com", 5, "business", 0.9)
    result = ce._dedupe([a, b])
    assert len(result) == 1
    # Keeps the higher-mention row.
    assert result[0].mentions == 5


def test_dedupe_folds_variants_by_normalised_name_when_no_domain():
    a = ce.ClassifiedCompetitor("ABC Jewellery Ltd", None, 3, "business", 0.9)
    b = ce.ClassifiedCompetitor("ABC Jewellery", None, 1, "business", 0.9)
    result = ce._dedupe([a, b])
    assert len(result) == 1 and result[0].mentions == 3


# ─── report filter ───────────────────────────────────────────────────────────


def test_filter_for_report_keeps_only_business_and_confident():
    items = ce._parse_response(_valid_payload())
    surfaced = ce.filter_for_report(items)
    names = {r["name"] for r in surfaced}
    # The two real jewellers pass; Lefkara Silver (adjacent) and The Cyprus
    # Guide (directory) do not — even though Lefkara's confidence is high, its
    # TYPE was correctly downgraded.
    assert names == {"Michalis Diamond Gallery", "Panos Melekkis"}
    assert all(set(r.keys()) == {"name", "mentions", "domain"} for r in surfaced)


def test_filter_respects_confidence_gate():
    low = [ce.ClassifiedCompetitor("Only Kinda", "kinda.com", 3, "business", 0.5)]
    assert ce.filter_for_report(low) == []


def test_filter_respects_limit():
    items = [
        ce.ClassifiedCompetitor(f"biz {i}", f"biz{i}.com", 10 - i, "business", 0.9)
        for i in range(30)
    ]
    assert len(ce.filter_for_report(items, limit=5)) == 5


# ─── outer function: monkeypatched HTTP ──────────────────────────────────────


def test_classify_competitors_end_to_end(monkeypatch):
    """Monkeypatch the HTTP layer — verify the full pipeline: build → post →
    parse → dedupe returns the expected shape."""
    monkeypatch.setattr(ce, "_post_openrouter", lambda **_: _valid_payload())
    out = ce.classify_competitors(
        name="Era More Than Gold", category="jewellery", city="Limassol",
        domain="eramorethangold.com",
        answers=[("Q", "AI mentioned Michalis Diamond Gallery and Panos Melekkis…")],
        candidate_domains=["thecyguide.com"],
        api_key="test-key",
    )
    assert {c.name for c in out} == {"Michalis Diamond Gallery", "Panos Melekkis", "Lefkara Silver", "The Cyprus Guide"}
    surfaced = ce.filter_for_report(out)
    # Report-shape output: only real competitors, ranked by mentions.
    assert [r["name"] for r in surfaced] == ["Michalis Diamond Gallery", "Panos Melekkis"]


def test_classify_raises_on_empty_answers():
    with pytest.raises(ce.CompetitorExtractionError):
        ce.classify_competitors(
            name="X", category=None, city=None, domain=None,
            answers=[], candidate_domains=[], api_key="k",
        )


def test_classify_raises_on_missing_api_key():
    with pytest.raises(ce.CompetitorExtractionError):
        ce.classify_competitors(
            name="X", category=None, city=None, domain=None,
            answers=[("Q", "A")], candidate_domains=[], api_key="",
        )
