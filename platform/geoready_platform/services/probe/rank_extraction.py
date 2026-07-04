"""Extract the ranked business list from each AI answer.

Perplexity, GPT, and Claude answers to "who are the top X in Y" questions
share a very predictable shape: numbered markdown headers with bolded
business names, e.g.

    ### 1. **Zacharias Watches & Jewellery**
    - **Brands**: Rolex, Omega, ...

    2. **A. Stephanides & Son**
    * **Location**: ...

This module extracts just the ranked business NAMES — no addresses, phones,
or descriptions. The report renders those extracted lists as compact matrix
rows so the buyer can see at a glance who AI is putting in which position,
without wading through 800 chars of prose per answer.

Pure regex. Bounded runtime. Never crashes: on any parse failure returns [].
"""

from __future__ import annotations

import re

# Match a numbered item at the start of a line (with optional markdown heading
# hashes and bullet stars), followed by ANY amount of whitespace, then either:
#   - a **bold** business name  (most common in Perplexity/GPT output)
#   - or a plain business name up to the first punctuation break
# The number capture (\d+) lets us skip runs that restart at 1 mid-answer.
_RANK_ROW = re.compile(
    r"""
    (?:^|\n)              # start of line
    \s{0,3}               # optional leading indent
    (?:\#{1,4}\s+)?       # optional markdown heading
    (?:[\*\-•]\s+)?       # optional bullet
    (\d{1,2})\.\s+        # NUMBER + dot + space  ← the ranking hook
    \*{0,2}               # optional bold-open
    ([^\n*:]{2,80})       # business name — stops at newline, star, or colon
    \*{0,2}               # optional bold-close
    """,
    re.VERBOSE,
)

# Trailing junk we don't want in a business-name capture.
_TRAILING_JUNK = re.compile(r"[\s\-—:,\.]+$")
_LEADING_JUNK = re.compile(r"^[\s\-—:,\.\*]+")

# Words a bare "1. Location" row would produce that AREN'T business names.
_NAME_STOPWORDS = frozenset({
    "location", "address", "phone", "email", "website", "hours",
    "specialty", "specialties", "brands", "services", "note", "notes",
    "contact", "why", "why visit", "features", "highlights", "products",
    "reviews", "rating", "the", "yes", "no",
})


def extract_ranked_names(text: str, *, limit: int = 10) -> list[str]:
    """Return up to ``limit`` business names in the order AI ranked them.

    Handles the most common patterns from Perplexity, GPT, and Claude. Runs
    of numbered lists that restart at 1 (e.g. sub-lists) are handled by keeping
    only the first monotonically increasing run — sub-lists are ignored.
    """
    if not text:
        return []

    matches = _RANK_ROW.findall(text)
    if not matches:
        return []

    seen: set[str] = set()
    out: list[str] = []
    last_num = 0

    for num_str, raw_name in matches:
        try:
            num = int(num_str)
        except ValueError:
            continue

        # A sub-list starts by resetting to a lower number. We treat "1" after
        # something higher as a new list (and stop) — otherwise we'd merge
        # "top 5 watch dealers" with "top 3 repair shops" further down.
        if num <= last_num and out:
            break
        last_num = num

        name = _LEADING_JUNK.sub("", raw_name).strip()
        name = _TRAILING_JUNK.sub("", name).strip()
        if not name or len(name) < 2:
            continue
        if name.lower() in _NAME_STOPWORDS:
            continue

        # Drop parenthetical suffixes describing the business (e.g. "Foo Ltd
        # (Official Rolex Dealer)"). Keep parentheticals INSIDE brand names.
        # Simple rule: strip a single trailing parenthetical.
        name = re.sub(r"\s*\([^()]{5,120}\)\s*$", "", name).strip()
        if not name:
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= limit:
            break

    return out


def brand_position(ranked_names: list[str], brand_name: str) -> int | None:
    """Return the 1-indexed position of the brand in the ranked list, or None.

    Word-boundary case-insensitive match — matches "Era More Than Gold" against
    "ERA More than Gold Ltd" (real AI output uses suffixes) without spuriously
    matching against unrelated names that share a substring."""
    if not brand_name or not ranked_names:
        return None
    needle = brand_name.lower().strip()
    if not needle:
        return None
    # Word-boundary regex so "A" doesn't hit "Era" and "Era" doesn't hit "Era-jul".
    pattern = re.compile(rf"\b{re.escape(needle)}\b", re.IGNORECASE)
    for i, name in enumerate(ranked_names, 1):
        n = name.lower()
        if needle == n or pattern.search(n):
            return i
    return None
