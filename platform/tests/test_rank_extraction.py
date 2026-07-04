"""Unit tests for the AI-answer ranking extractor.

Feed representative snippets of real Perplexity, GPT, and Claude output
and check we pull out clean ordered business names — no addresses,
phones, or descriptions."""

from __future__ import annotations

from geoready_platform.services.probe.rank_extraction import (
    brand_position, extract_ranked_names,
)


def test_extracts_perplexity_style_h3_headers():
    """The most common Perplexity shape: `### N. **Name**` with details under."""
    text = """\
Here are the top jewellers in Limassol:

### 1. **Michalis Diamond Gallery**
- **Specialty:** High jewellery, luxury timepieces
- **Address:** 89 Georgiou A, Limassol
- **Contact:** +357 25 312071

### 2. **A. Stephanides & Son**
- **Location:** Makarios Avenue
- **Phone:** +357 25 587949

### 3. **Nikos Ioannou Jewellers**
- **Address:** Makarios III Avenue 242
"""
    names = extract_ranked_names(text)
    assert names == ["Michalis Diamond Gallery", "A. Stephanides & Son", "Nikos Ioannou Jewellers"]


def test_extracts_bare_numbered_list():
    """GPT / Claude often skip the heading and just start numbers."""
    text = """\
Based on your query:

1. **Zacharias Watches & Jewellery** — Rolex, Omega authorised dealer
2. **A. Stephanides & Son** — legacy institution
3. **Kings Jewellers** — Tissot store

Contact them directly for pricing.
"""
    names = extract_ranked_names(text)
    assert names == ["Zacharias Watches & Jewellery", "A. Stephanides & Son", "Kings Jewellers"]


def test_handles_h4_bullets_and_mixed_markdown():
    text = """\
#### 1. **Panos Melekkis Jewellery**
* Location: Limassol Marina
#### 2. **LITES Jewelry**
- Note: silver specialists
#### 3. **Christian Xenon**
"""
    assert extract_ranked_names(text) == [
        "Panos Melekkis Jewellery", "LITES Jewelry", "Christian Xenon",
    ]


def test_stops_at_sublist_restart():
    """A common failure mode: prose that lists top-3 shops, then restarts
    a numbered list under one shop. We must not merge them into one long list."""
    text = """\
Top shops:

1. **Michalis Diamond Gallery**
   Their services include:
   1. Custom design
   2. Watch repair
2. **Aquarius Jewellery**
"""
    names = extract_ranked_names(text)
    # Sub-list resets to 1 → we stop and return just what came before.
    assert names[0] == "Michalis Diamond Gallery"
    # Aquarius is separated by the sub-list — acceptable to drop it here.
    assert "Aquarius Jewellery" not in names or names == ["Michalis Diamond Gallery"]


def test_dedupes_by_case_insensitive_name():
    text = """\
1. **Panos Melekkis Jewellery** — engagement rings
2. **Aquarius Jewellery**
3. **panos melekkis jewellery** — duplicate row, different casing
"""
    names = extract_ranked_names(text)
    assert len(names) == 2
    assert names[0].lower() == "panos melekkis jewellery"


def test_strips_trailing_parenthetical_descriptions():
    """AI often appends descriptors: 'Foo Ltd (Official Rolex Dealer)'."""
    text = "1. **A. Stephanides & Son (Official Rolex & Chopard Dealer)**"
    names = extract_ranked_names(text)
    assert names == ["A. Stephanides & Son"]


def test_drops_stopword_only_rows():
    """A numbered 'Location: Limassol Marina' row must not become a business."""
    text = """\
1. Location: Limassol Marina
2. Address: 123 Main St
3. **Michalis Diamond Gallery**
"""
    # We drop Location/Address rows entirely — but the numbering monotonicity
    # rule then makes 3 a valid next row.
    names = extract_ranked_names(text)
    assert "Michalis Diamond Gallery" in names
    assert not any(n.lower().startswith("location") for n in names)


def test_respects_limit():
    lines = "\n".join(f"{i}. **Business {i}**" for i in range(1, 20))
    assert len(extract_ranked_names(lines, limit=5)) == 5
    assert len(extract_ranked_names(lines, limit=10)) == 10


def test_returns_empty_on_prose_without_numbered_lists():
    text = """\
Era More Than Gold appears to be a reputable jewellery store based in Cyprus
with locations in Paphos and Limassol. They carry Breitling and Tissot watches.
"""
    assert extract_ranked_names(text) == []


def test_returns_empty_on_empty_input():
    assert extract_ranked_names("") == []
    assert extract_ranked_names(None) == []  # type: ignore[arg-type]


def test_brand_position_exact_match():
    ranked = ["Michalis Diamond Gallery", "Era More Than Gold", "Panos Melekkis"]
    assert brand_position(ranked, "Era More Than Gold") == 2


def test_brand_position_case_insensitive_contains():
    """Real answers write 'ERA More than Gold Ltd' — we still want to match."""
    ranked = ["Michalis Diamond Gallery", "ERA More than Gold Ltd", "Panos Melekkis"]
    assert brand_position(ranked, "Era More Than Gold") == 2


def test_brand_position_returns_none_when_absent():
    assert brand_position(["A", "B", "C"], "Era More Than Gold") is None
    assert brand_position([], "Era More Than Gold") is None
    assert brand_position(["A"], "") is None
