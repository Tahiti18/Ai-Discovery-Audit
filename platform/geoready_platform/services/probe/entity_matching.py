"""Canonical entity (brand) matching for the Perception Probe.

WHY THIS EXISTS
---------------
v1 detected a brand by exact, case-insensitive *substring* of the full name.
That produces **false Share-of-Model zeros**: a business stored as "Acme
Plumbing LLC" is missed when the answer says "Acme Plumbing", "Acme's plumbing",
"ACME", or "Acmé". Since SoM is mention-based, a missed mention silently reads as
"AI never recommends you" — the most damaging possible error. This module makes
the mention test robust while staying precision-first.

THE PIPELINE
------------
1. Normalize both the brand variants and the answer text identically:
   - Unicode NFKD + strip accents      (café -> cafe)            [intl support]
   - lowercase                          (ACME -> acme)            [case-insensitive]
   - & / +  ->  "and"                   (B&B -> b and b)          [symbol words]
   - strip possessives "'s"/"’s"        (Acme's -> acme)          [possessive]
   - drop remaining apostrophes         (O'Brien -> obrien)
   - non-alphanumerics -> space         ("Acme, Inc." -> acme inc)[punctuation]
   - singularize tokens len>4 ending s  (acmes->acme, plumbings->plumbing)
                                                                  [possessive-without-apostrophe + plurals]
2. Build brand VARIANTS: full name; name minus business suffix (Inc/LLC/Ltd/
   GmbH/PLC/…); configured aliases; domain-derived label; optional acronym; and
   the first distinctive token of the core name.
3. Match: multi-token variants must appear as a CONTIGUOUS token sequence
   (phrase match — high precision). Single-token variants must appear as a whole
   token and be distinctive (len>=3, not a generic/category word).

TRADEOFFS (read before trusting it)
-----------------------------------
- Token singularization (drop trailing 's' for len>4) fixes possessive/plural
  recall but can over-merge rare words ("address"->"addres"); applied to BOTH
  sides so matching stays consistent. Net win.
- Single-token matching (first distinctive token, domain label, acronym) buys
  recall on partial mentions but is the main false-positive risk for ambiguous
  single-word brands (e.g. "Apple" matches "apple pie"). We accept this: missing
  a real mention (false SoM zero) is worse than an occasional over-count, and
  ambiguous single-word brands are inherently unresolvable without context.
- NO fuzzy/edit-distance matching: misspellings are NOT caught, by choice —
  fuzzy matching would explode false positives. Precision over typo-recall.
- NO transliteration: a Latin brand name will not match non-Latin script text
  (Japanese/Cyrillic/Arabic) because normalization drops non-ASCII. Known gap.
- Acronym generation is OFF by default (3-letter acronyms collide constantly);
  enable per-call only when the brand is genuinely acronym-identified.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Business/legal suffixes stripped to form the "core" name variant.
_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "co", "corp", "corporation",
        "company", "gmbh", "plc", "sa", "sas", "srl", "spa", "pty", "ag", "bv",
        "oy", "ab", "as", "kk", "lp", "llp", "group", "holdings", "ug", "kg",
    }
)

# Generic words that must not, alone, constitute a brand mention.
_GENERIC: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "for", "in", "of", "at", "on", "to", "by",
        "best", "top", "near", "me", "my", "your", "local", "service", "store",
        "shop", "online", "app", "group", "company", "co", "inc", "studio",
        "center", "centre", "clinic", "house", "home",
    }
)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _singularize(token: str) -> str:
    return token[:-1] if len(token) > 4 and token.endswith("s") else token


def normalize(s: str) -> str:
    """Canonical form. See module docstring for each rule + rationale."""
    s = _strip_accents(s or "").lower()
    s = s.replace("&", " and ").replace("+", " and ")
    s = re.sub(r"['’`´]s\b", "", s)       # possessive 's
    s = re.sub(r"['’`´]", "", s)          # other apostrophes
    s = re.sub(r"[^a-z0-9]+", " ", s)     # punctuation -> space (drops non-ASCII)
    tokens = [_singularize(t) for t in s.split()]
    return " ".join(tokens).strip()


def _tokens(s: str) -> list[str]:
    return normalize(s).split()


def _strip_suffix(tokens: list[str]) -> list[str]:
    out = list(tokens)
    while len(out) > 1 and out[-1] in _SUFFIXES:
        out.pop()
    return out


def _domain_label(domain: str) -> str:
    d = (domain or "").strip().lower()
    if "://" in d:
        d = d.split("://", 1)[1]
    d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    parts = [p for p in d.split(".") if p]
    if not parts:
        return ""
    # registrable label: second-to-last for multi-part, else the only part
    label = parts[-2] if len(parts) >= 2 else parts[0]
    return _singularize(label)


@dataclass
class MatchResult:
    matched: bool
    variant: str = ""
    kind: str = ""  # full | core | alias | domain | acronym | token


def _contiguous(needle: list[str], hay: list[str]) -> bool:
    if not needle or len(needle) > len(hay):
        return False
    n = len(needle)
    return any(hay[i : i + n] == needle for i in range(len(hay) - n + 1))


def build_variants(
    name: str,
    *,
    domain: str | None = None,
    aliases: list[str] | None = None,
    category: str | None = None,
    enable_acronym: bool = False,
) -> tuple[list[tuple[list[str], str]], list[tuple[str, str]]]:
    """Return (phrase_variants, single_token_variants).

    phrase_variants: list of (token_list, kind) matched as contiguous sequences.
    single_token_variants: list of (token, kind) matched as whole distinctive tokens.
    """
    phrases: list[tuple[list[str], str]] = []
    singles: list[tuple[str, str]] = []
    seen_phrase: set[tuple[str, ...]] = set()
    seen_single: set[str] = set()
    generic = set(_GENERIC) | set(_tokens(category or ""))

    def add_phrase(toks: list[str], kind: str) -> None:
        key = tuple(toks)
        if not toks or key in seen_phrase:
            return
        # A name made entirely of generic/category words ("Best Dentist") is not
        # distinctive — matching it would fire on ordinary category prose. Skip.
        # Consequence: businesses named only with generic words can't be
        # detected; rare and inherently ambiguous (documented limitation).
        if all(t in generic for t in toks):
            return
        seen_phrase.add(key)
        if len(toks) == 1:
            add_single(toks[0], kind)
        else:
            phrases.append((toks, kind))

    def add_single(tok: str, kind: str, *, trusted: bool = False) -> None:
        if not tok or tok in seen_single:
            return
        # Distinctiveness guard: long enough and not a generic/category word,
        # unless it's a trusted identifier (domain/alias/acronym).
        if not trusted and (len(tok) < 3 or tok in generic):
            return
        if len(tok) < 3:
            return
        seen_single.add(tok)
        singles.append((tok, kind))

    full = _tokens(name)
    core = _strip_suffix(full)
    add_phrase(full, "full")
    add_phrase(core, "core")

    for alias in aliases or []:
        at = _tokens(alias)
        add_phrase(at, "alias")
        add_phrase(_strip_suffix(at), "alias")

    label = _domain_label(domain or "")
    if label:
        add_single(label, "domain", trusted=True)

    # First distinctive token of the core name (covers partial mentions).
    for tok in core:
        if len(tok) >= 4 and tok not in generic:
            add_single(tok, "token")
            break

    if enable_acronym and len(core) >= 2:
        acr = "".join(t[0] for t in core if t)
        if len(acr) >= 3:
            add_single(acr, "acronym", trusted=True)

    return phrases, singles


def mentions(
    text: str,
    name: str,
    *,
    domain: str | None = None,
    aliases: list[str] | None = None,
    category: str | None = None,
    enable_acronym: bool = False,
) -> MatchResult:
    """True if ``text`` mentions the business ``name`` (robust, precision-first)."""
    if not name or not text:
        return MatchResult(False)
    htoks = _tokens(text)
    if not htoks:
        return MatchResult(False)

    phrases, singles = build_variants(
        name, domain=domain, aliases=aliases, category=category, enable_acronym=enable_acronym
    )
    for toks, kind in phrases:
        if _contiguous(toks, htoks):
            return MatchResult(True, " ".join(toks), kind)
    hset = set(htoks)
    for tok, kind in singles:
        if tok in hset:
            return MatchResult(True, tok, kind)
    return MatchResult(False)
