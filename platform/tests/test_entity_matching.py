"""Canonical entity matching — regression + adversarial cases.

Split into:
- SHOULD match (recall the v1 exact-substring matcher would have missed)
- SHOULD NOT match (precision guards)
- DOCUMENTED LIMITATIONS (asserted to lock in known behavior, not aspirational)
"""

from __future__ import annotations

import pytest

from geoready_platform.services.probe.entity_matching import mentions, normalize

# ─── normalization ───────────────────────────────────────────────────────────


def test_normalize_rules():
    assert normalize("Acme, Inc.") == "acme inc"
    assert normalize("Café Plumbing") == "cafe plumbing"
    assert normalize("B&B Services") == "b and b service"  # & -> and, singularize
    assert normalize("O'Brien's") == "obrien"  # possessive + apostrophe
    assert normalize("ACME   Plumbing") == "acme plumbing"


# ─── SHOULD match (recall wins over v1 exact substring) ──────────────────────

SHOULD_MATCH = [
    ("Acme Plumbing LLC", "We recommend Acme Plumbing for your needs.", None),      # suffix in name only
    ("Acme Plumbing", "Acme Plumbing, LLC is highly rated.", None),                 # suffix in text only
    ("Acme Plumbing", "Have you tried Acme's plumbing services?", None),            # possessive
    ("Acme Plumbing", "ACME PLUMBING is open now.", None),                          # case
    ("Café Lumière", "We loved Cafe Lumiere downtown.", None),                      # accents
    ("Acme Plumbing", "Acme is a solid choice.", None),                            # partial (first token)
    ("Joe's Plumbing", "Joes Plumbing did great work.", None),                      # possessive w/o apostrophe
    ("Smith & Sons", "Smith and Sons handled the job.", None),                      # & -> and
    ("Acme Plumbing", 'The guide lists "Acme Plumbing" as top rated.', None),       # quoted
    ("Northwind Plumbers", "Northwind Plumber was punctual.", None),                # plural/singular
]


@pytest.mark.parametrize("name,text,category", SHOULD_MATCH)
def test_should_match(name, text, category):
    assert mentions(text, name, category=category).matched, (name, text)


def test_domain_derived_name_matches():
    # Business stored with a different display name; the answer uses the domain brand.
    assert mentions("People love Notion for notes.", "Notion Labs", domain="notion.so").matched


def test_alias_matches():
    assert mentions("KFC has the best fried chicken.", "Kentucky Fried Chicken", aliases=["KFC"]).matched


def test_acronym_opt_in():
    assert mentions("IBM dominates enterprise.", "International Business Machines", enable_acronym=True).matched
    # Off by default (acronyms collide): without opt-in, the 3-letter acronym is not generated.
    assert not mentions("the ibm standard applies", "International Business Machines").matched


# ─── SHOULD NOT match (precision guards) ─────────────────────────────────────

SHOULD_NOT_MATCH = [
    ("Acme Plumbing", "We used Globex Plumbing instead.", None),                    # different brand
    ("Acme Plumbing", "Plumbing services are widely available.", "plumbing"),       # category word only
    ("Best Dentist", "Find the best dentists in Denver.", "dentist"),              # generic name tokens
    ("Acme Plumbing", "The acmecorp tool is unrelated.", None),                     # substring, not token
    ("Home Services Co", "We offer home improvement help.", "home services"),       # generic 'home' guarded
]


@pytest.mark.parametrize("name,text,category", SHOULD_NOT_MATCH)
def test_should_not_match(name, text, category):
    assert not mentions(text, name, category=category).matched, (name, text)


# ─── DOCUMENTED LIMITATIONS (locked-in known behavior) ───────────────────────


def test_limitation_ambiguous_single_word_brand_overmatches():
    # "Apple" the brand matches "apple pie" — inherent ambiguity for single-word
    # brands. Documented tradeoff (we favor recall of real mentions).
    assert mentions("I baked an apple pie.", "Apple").matched


def test_limitation_misspellings_not_caught():
    # No fuzzy matching by design (precision over typo recall).
    assert not mentions("Acmee Plumbing is great.", "Acme Plumbing").matched


def test_limitation_non_latin_script_not_matched():
    # No transliteration: Latin brand name vs Japanese text does not match.
    assert not mentions("東京の歯科医院。", "Sakura Dental").matched
