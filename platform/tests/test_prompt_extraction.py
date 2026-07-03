"""Unit tests for the LLM-generated buyer-question generator.

The HTTP call itself is monkeypatched — these tests exercise prompt shape,
JSON parsing, the discovery/branded invariant, and the JSON storage roundtrip.
"""

from __future__ import annotations

import pytest

from geoready_platform.services.probe import prompt_extraction as pe


# ─── prompt shape ────────────────────────────────────────────────────────────


def test_build_prompt_includes_all_facts_and_category_menu():
    p = pe.build_prompt(
        name="Era More Than Gold", category="jewellery + Swiss watches",
        city="Limassol", domain="eramorethangold.com", target_count=15,
    )
    assert "Era More Than Gold" in p
    assert "jewellery + Swiss watches" in p and "Limassol" in p
    assert "eramorethangold.com" in p
    for cat in pe._VALID_CATEGORIES:
        assert cat in p
    # 15 total, 5 branded (15//3), 10 discovery — adaptive to target_count.
    assert "10 of the 15" in p and "5 of the 15" in p


def test_build_prompt_includes_website_snippet_when_provided():
    """The homepage text is what enables product/brand-specific queries."""
    p = pe.build_prompt(
        name="X", category="jewellers", city="Y", domain="x.com",
        website_snippet="We are an authorised dealer for Breitling, Chopard, and Rado.",
    )
    assert "Breitling, Chopard, and Rado" in p
    assert "long-tail" in p.lower()


# ─── parser + invariants ─────────────────────────────────────────────────────


def _valid_payload(name="Era More Than Gold") -> str:
    return (
        '{"prompts":['
        # 5 discovery (no name)
        '{"text":"Where can I buy a Breitling watch in Limassol?","category":"problem_solution"},'
        '{"text":"What are the best jewellers in Limassol?","category":"category_recommendation"},'
        '{"text":"Recommend a Cartier dealer in Limassol","category":"problem_solution"},'
        '{"text":"Best place for engagement rings in Cyprus","category":"category_recommendation"},'
        '{"text":"Who sells Chopard watches near Limassol?","category":"category_recommendation"},'
        # 3 branded (must contain name)
        f'{{"text":"What are the best alternatives to {name} in Limassol?","category":"comparison"}},'
        f'{{"text":"Is {name} a trustworthy jeweller?","category":"legitimacy"}},'
        f'{{"text":"Tell me about {name}","category":"awareness"}}'
        ']}'
    )


def test_parse_clean_payload_returns_all_eight():
    items = pe._parse_response(_valid_payload(), name="Era More Than Gold")
    assert len(items) == 8


def test_parse_drops_discovery_prompt_containing_the_brand_name():
    """A discovery template that leaks the name would contaminate Share-of-Model.
    Enforce the invariant at parse time."""
    bad = (
        '{"prompts":['
        '{"text":"What are the best alternatives to Era More Than Gold?","category":"category_recommendation"}'
        ']}'
    )
    items = pe._parse_response(bad, name="Era More Than Gold")
    assert items == []  # dropped — was a name-bearing "discovery"


def test_parse_drops_branded_prompt_missing_the_brand_name():
    """A branded template that forgot the name gives us no signal — drop it."""
    bad = (
        '{"prompts":['
        '{"text":"Is this jewellery shop reputable?","category":"legitimacy"}'
        ']}'
    )
    items = pe._parse_response(bad, name="Era More Than Gold")
    assert items == []


def test_parse_drops_rows_with_unknown_category():
    items = pe._parse_response(
        '{"prompts":[{"text":"Best jewellers?","category":"made_up_kind"}]}',
        name="Era",
    )
    assert items == []


def test_parse_strips_markdown_fences():
    fenced = f"Here you go:\n```json\n{_valid_payload()}\n```"
    items = pe._parse_response(fenced, name="Era More Than Gold")
    assert len(items) == 8


def test_parse_rejects_invalid_json():
    with pytest.raises(pe.PromptGenerationError):
        pe._parse_response("not json", name="Era")


def test_parse_rejects_missing_prompts_key():
    with pytest.raises(pe.PromptGenerationError):
        pe._parse_response('{"items":[]}', name="Era")


# ─── storage roundtrip ──────────────────────────────────────────────────────


def test_to_json_from_json_roundtrip():
    original = pe._parse_response(_valid_payload(), name="Era More Than Gold")
    revived = pe.from_json(pe.to_json(original))
    assert len(revived) == len(original)
    assert [p.text for p in revived] == [p.text for p in original]
    assert [p.category for p in revived] == [p.category for p in original]


def test_from_json_tolerates_garbage_rows():
    items = pe.from_json([
        {"text": "ok", "category": "category_recommendation"},
        {"text": "", "category": "category_recommendation"},   # empty text
        {"text": "ok2", "category": "bogus"},                   # bad category
        "not a dict",                                            # wrong shape
        None,
    ])
    assert [p.text for p in items] == ["ok"]


# ─── outer function: monkeypatched HTTP ─────────────────────────────────────


def test_generate_prompts_for_entity_end_to_end(monkeypatch):
    monkeypatch.setattr(pe, "_post_openrouter", lambda **_: _valid_payload())
    prompts = pe.generate_prompts_for_entity(
        name="Era More Than Gold", category="jewellery", city="Limassol",
        domain="eramorethangold.com", api_key="test",
    )
    assert len(prompts) == 8
    disc = [p for p in prompts if p.category in ("category_recommendation", "problem_solution")]
    brand = [p for p in prompts if p.category in ("comparison", "legitimacy", "awareness", "factual_attributes")]
    assert len(disc) == 5 and len(brand) == 3


def test_generate_requires_mixed_output(monkeypatch):
    """Discovery-only output is refused so the caller falls back to templates."""
    only_discovery = (
        '{"prompts":[{"text":"Best jewellers in Limassol?","category":"category_recommendation"}]}'
    )
    monkeypatch.setattr(pe, "_post_openrouter", lambda **_: only_discovery)
    with pytest.raises(pe.PromptGenerationError):
        pe.generate_prompts_for_entity(
            name="Era More Than Gold", category="jewellery", city="Limassol",
            domain=None, api_key="test",
        )


def test_generate_raises_on_missing_api_key():
    with pytest.raises(pe.PromptGenerationError):
        pe.generate_prompts_for_entity(
            name="Era", category=None, city=None, domain=None, api_key="",
        )


def test_generate_raises_on_missing_name():
    with pytest.raises(pe.PromptGenerationError):
        pe.generate_prompts_for_entity(
            name="   ", category=None, city=None, domain=None, api_key="k",
        )
