"""LLM-based competitor extraction.

Takes the 8 raw AI answers a probe collected and classifies who's actually a
competitor — i.e. a business a real buyer would consider INSTEAD of the entity.
Replaces the URL-count + static-denylist output with something semantically
validated by an LLM.

Why an LLM: url counting can't distinguish "same category, different buyer
intent" (e.g. Lefkara Silver — traditional tourist silverware — is jewellery-
adjacent to Era More Than Gold's fine jewellery + Swiss watches, but a Breitling
buyer won't consider it instead). It also misses businesses named in the answer
TEXT without a URL citation. The classifier reads all 8 answers together and
returns a clean, ranked, deduplicated list.

Design contract:
- Pure over inputs — no DB access, no globals.
- Bounded cost: one HTTP call, hard 15s timeout, single retry.
- Never crashes a probe run: on any failure (network, malformed JSON, empty),
  raises CompetitorExtractionError; caller falls back to the URL+denylist list.
- Uses OpenRouter's model-fallback so Sonnet takes over if Haiku is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Anthropic models via OpenRouter. Haiku 4.5 is the classification sweet spot;
# Sonnet 4.5 is the automatic fallback if the primary is unavailable.
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
FALLBACK_MODELS = ("anthropic/claude-sonnet-4.5",)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 15.0
_MAX_OUTPUT_CHARS = 8_000  # trims freakishly long JSON blobs before parsing
_EXTRACTION_VERSION = "extract_v1"  # bump when the prompt/schema changes


class CompetitorExtractionError(Exception):
    """Raised when the classifier fails; caller falls back to the legacy list."""


@dataclass(frozen=True)
class ClassifiedCompetitor:
    """One row of the classifier's output. Only ``type='business'`` rows with
    ``confidence >= 0.7`` are surfaced in the report; the rest are for logs."""

    name: str
    domain: str | None
    mentions: int
    type: str  # "business" | "adjacent" | "directory" | "reference" | "self"
    confidence: float
    why: str = ""


_SYSTEM_PROMPT = """\
You are a competitive-intelligence analyst. Given AI answers about a business,
identify the businesses a real BUYER would consider instead of it.

Return valid JSON only — no markdown, no prose outside the JSON.
"""


def build_prompt(
    *,
    name: str,
    category: str | None,
    city: str | None,
    domain: str | None,
    answers: list[tuple[str, str]],  # [(prompt_question, raw_answer_text), ...]
    candidate_domains: list[str],    # domains AI already cited (hint)
) -> str:
    """Produce the user prompt for the classifier. Pure — trivially testable."""
    entity_lines = [
        f"- Name: {name}",
        f"- Sells: {category or 'unknown'}",
        f"- Location: {city or 'unknown'}",
    ]
    if domain:
        entity_lines.append(f"- Website: {domain}")

    answer_blocks = []
    for i, (q, a) in enumerate(answers, 1):
        answer_blocks.append(f"Question {i}: {q}\nAnswer: {a}")
    answers_txt = "\n\n".join(answer_blocks) if answer_blocks else "(no answers)"

    hint = ", ".join(candidate_domains[:30]) if candidate_domains else "(none)"

    return f"""\
Business being analyzed:
{chr(10).join(entity_lines)}

TASK: For each business or domain the AI answers below name, decide whether a
real buyer of {name}'s products would CONSIDER IT AS AN ALTERNATIVE.

Same buyer intent matters more than shared category. Example: a store selling
luxury Swiss watches and fine gold jewellery is NOT competing with a shop
selling traditional tourist silver filigree — even though both are "jewellery".
A buyer choosing a Breitling watch will not consider tourist silverware
instead.

Classify each candidate:
- "business": a real business a buyer of {name} would realistically consider
  instead — same sub-category, same rough price tier, same location area.
- "adjacent": category-adjacent but NOT what this buyer would consider instead
  (different sub-category or price tier).
- "directory": listing/review/tourism/aggregator sites (e.g. tripadvisor,
  tourism guides, city directories, yellowpages).
- "reference": Wikipedia, news, generic reference sites.
- "self": {name} itself, or an obvious mirror/subdomain.

Rules:
- Extract businesses named in the answer TEXT even if no URL is cited.
- Deduplicate variants ("ABC Jewellery Ltd" + "ABC Jewellery" = one entry, use
  the shortest clean form).
- Count how many of the {len(answer_blocks)} answers named each one.
- Only include items with confidence >= 0.7.
- Return the top 20 by mentions.
- One-line "why" for each — the reason it belongs in that class.

Return JSON EXACTLY like this (no other keys, no trailing text):
{{"competitors":[{{"name":"...","domain":"...","mentions":1,"type":"business","confidence":0.9,"why":"..."}}]}}

AI answers:
---
{answers_txt}
---

Domains AI already cited (evidence hint): {hint}
"""


def classify_competitors(
    *,
    name: str,
    category: str | None,
    city: str | None,
    domain: str | None,
    answers: list[tuple[str, str]],
    candidate_domains: list[str],
    api_key: str,
    model: str | None = None,
) -> list[ClassifiedCompetitor]:
    """Call the LLM classifier and return the parsed list.

    Raises ``CompetitorExtractionError`` on any failure so the caller can fall
    back to the legacy URL+denylist output. Never returns a partial result.
    """
    if not api_key:
        raise CompetitorExtractionError("No OpenRouter key configured")
    if not answers:
        raise CompetitorExtractionError("No answers to classify")

    prompt = build_prompt(
        name=name, category=category, city=city, domain=domain,
        answers=answers, candidate_domains=candidate_domains,
    )
    raw = _post_openrouter(prompt=prompt, api_key=api_key, model=model or DEFAULT_MODEL)
    parsed = _parse_response(raw)
    return _dedupe(parsed)


def _post_openrouter(*, prompt: str, api_key: str, model: str) -> str:
    """Single OpenRouter POST with automatic model-fallback + JSON mode."""
    import httpx

    body = {
        "model": model,
        # `models` triggers OpenRouter's server-side fallback if the primary
        # is overloaded or unavailable — no extra client round-trip.
        "models": [model, *FALLBACK_MODELS],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # Ask the router for JSON. Some providers ignore this; the parser is
        # defensive about markdown fences either way.
        "response_format": {"type": "json_object"},
        "temperature": 0.2,  # bounded creativity — this is classification, not writing
    }
    try:
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # OpenRouter attribution — nice to have, no impact if omitted.
                "HTTP-Referer": os.environ.get("GR_APP_BASE_URL", "http://localhost:4321"),
                "X-Title": "Visible to AI",
            },
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — never leak the key
        raise CompetitorExtractionError(f"OpenRouter call failed: {type(exc).__name__}") from exc

    try:
        data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as exc:  # noqa: BLE001
        raise CompetitorExtractionError(f"Malformed OpenRouter response: {exc}") from exc
    if not content:
        raise CompetitorExtractionError("Empty content from classifier")
    return content[:_MAX_OUTPUT_CHARS]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(raw: str) -> list[ClassifiedCompetitor]:
    """Parse the classifier's JSON. Tolerates markdown fences some models emit."""
    text = raw.strip()
    # Strip a possible ```json … ``` fence (Anthropic doesn't add them, but some
    # fallback providers do, so we're defensive without being clever).
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CompetitorExtractionError(f"Invalid JSON: {exc}") from exc
    items = obj.get("competitors") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise CompetitorExtractionError("JSON missing 'competitors' list")

    out: list[ClassifiedCompetitor] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        try:
            mentions = int(row.get("mentions") or 0)
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        out.append(ClassifiedCompetitor(
            name=name,
            domain=(str(row.get("domain")).strip() or None) if row.get("domain") else None,
            mentions=max(0, mentions),
            type=str(row.get("type") or "unknown").strip().lower(),
            confidence=max(0.0, min(1.0, confidence)),
            why=str(row.get("why") or "").strip()[:280],
        ))
    return out


def _dedupe(items: list[ClassifiedCompetitor]) -> list[ClassifiedCompetitor]:
    """Fold obvious duplicates (same domain, or same normalised name)."""
    seen: dict[str, ClassifiedCompetitor] = {}
    for c in items:
        key = (c.domain or "").lower().strip() or _norm_name(c.name)
        if not key:
            continue
        existing = seen.get(key)
        if existing is None or c.mentions > existing.mentions:
            seen[key] = c
    return sorted(seen.values(), key=lambda x: (-x.mentions, x.name.lower()))


def _norm_name(name: str) -> str:
    """Cheap normalisation for dedupe: lowercase, strip legal suffixes/spaces."""
    n = name.lower().strip()
    for suffix in (" ltd", " limited", " inc", " llc", " co", " sa", " gmbh", " ltd."):
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return re.sub(r"\s+", " ", n)


def filter_for_report(items: list[ClassifiedCompetitor], *, min_confidence: float = 0.7, limit: int = 20) -> list[dict]:
    """Convert to the shape the ProbeRun.competitors JSON column expects, keeping
    only businesses a buyer would genuinely consider (type='business', confident)."""
    kept = [c for c in items if c.type == "business" and c.confidence >= min_confidence]
    return [{"name": c.name, "mentions": c.mentions, "domain": c.domain} for c in kept[:limit]]
