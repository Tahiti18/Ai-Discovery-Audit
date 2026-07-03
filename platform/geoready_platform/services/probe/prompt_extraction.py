"""LLM-generated buyer questions, per business.

Ships one Haiku 4.5 call per business (on first probe run only) that reads the
business's identity and produces the actual questions a real buyer would ask AI
about that category and location — replacing the generic static templates that
don't fit product businesses (jewellers, bakers, retailers).

Called once per entity; the result is cached on ``BusinessEntity.custom_prompts``
so trend comparisons across runs stay clean. Only regenerated when the version
string bumps (schema change) or an operator explicitly clears the cache.

Design contract:
- Pure over inputs — no DB access, no globals.
- Bounded cost: one HTTP call, hard timeout, single retry via OpenRouter fallback.
- Never crashes a probe run: on any failure raises PromptGenerationError; caller
  falls back to the static template generator.
- Every generated prompt is validated against the known taxonomy category set —
  the LLM cannot invent a category we don't handle downstream.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
FALLBACK_MODELS = ("anthropic/claude-sonnet-4.5",)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 20.0
_MAX_OUTPUT_CHARS = 10_000

# Bump when the generator prompt/schema changes materially — cached prompts on
# older versions get regenerated on next run.
# v2: expanded to 15 prompts and website-informed (adds long-tail product/brand
#     queries like "Breitling Limassol" when the site actually mentions them).
GENERATOR_VERSION = "gen_v2"

# How many prompts to ask the generator for. Sits alongside `probe_max_prompts`
# — the runner takes at most `probe_max_prompts` from the generated set.
DEFAULT_TARGET_COUNT = 15

# The exact category keys the probe pipeline understands. Kept in step with
# taxonomy.CATEGORIES; if the LLM invents anything else, we drop that prompt.
_VALID_CATEGORIES = {
    "category_recommendation",  # discovery, no name (counts for SoM)
    "problem_solution",         # discovery, no name (counts for SoM)
    "comparison",               # branded (alternatives to X)
    "legitimacy",               # branded (is X reputable)
    "factual_attributes",       # branded (hours, location, services)
    "awareness",                # branded (tell me about X)
}


class PromptGenerationError(Exception):
    """Raised when generation fails; caller falls back to static templates."""


@dataclass(frozen=True)
class GeneratedPrompt:
    """One LLM-generated buyer question tagged with a taxonomy category."""

    text: str
    category: str  # one of _VALID_CATEGORIES


_SYSTEM_PROMPT = """\
You generate realistic buyer questions to test how well an AI answer engine
recommends a specific business. Write questions the way a real customer would
type them into ChatGPT, Perplexity, or Google AI — casual, specific, natural.

Return valid JSON only — no markdown fences, no prose outside the JSON.
"""


def build_prompt(
    *, name: str, category: str | None, city: str | None,
    domain: str | None, website_snippet: str | None = None,
    target_count: int = DEFAULT_TARGET_COUNT,
) -> str:
    """Produce the user prompt for the generator. Pure — trivially testable.

    When ``website_snippet`` is provided, the LLM extracts specific product /
    brand / service mentions from the site and writes long-tail queries around
    them (e.g. "Breitling Limassol", "engagement rings Limassol"). This is
    where product-specific questions come from.
    """
    entity_lines = [
        f"- Name: {name}",
        f"- Category / offering: {category or 'unknown'}",
        f"- Location: {city or 'unknown'}",
    ]
    if domain:
        entity_lines.append(f"- Website: {domain}")

    website_block = ""
    if website_snippet:
        website_block = (
            "\nThe business's homepage says the following (use this to identify "
            "SPECIFIC products, brands, and services they sell — then write "
            "long-tail buyer queries around those exact items):\n"
            "---\n"
            f"{website_snippet}\n"
            "---\n"
        )

    # Split target_count into ~2/3 discovery + ~1/3 branded, adaptive.
    n_branded = max(3, target_count // 3)
    n_discovery = target_count - n_branded

    return f"""\
Business we're auditing:
{chr(10).join(entity_lines)}
{website_block}
Generate exactly {target_count} realistic buyer questions to test AI visibility
for this business. Mix them across these two groups:

GROUP A — "Discovery" questions ({n_discovery} of the {target_count}). Do NOT
mention the business by name. These test whether AI recommends this kind of
business (or its specific products) to a stranger. Cover a mix of:
- Generic category recommendation ("best X in Y", "top X in Y") — 2–3 of these
- **Product / brand / service specifics — this is the most important group.**
  If the site mentions specific brands (e.g. Breitling, Chopard, Rado, Tissot,
  Cartier, TAG Heuer, Hamilton, Longines, etc.), specific services (watch
  repair, appraisal, engagement rings, custom design), or specific product
  categories (Swiss watches, diamond rings, gold chains, silver pieces), write
  queries around those EXACT items. Example shapes:
    * "{{brand}} dealer in {{city}}"
    * "where to buy {{brand}} watches {{city}}"
    * "{{service}} in {{city}}"
    * "{{specific product}} in {{city}}"
- Buying intent / situational ("I want to buy X in Y", "where do people go for X")
- Price / quality tier where obvious ("luxury X in Y", "affordable X in Y")

Prefer long-tail product-specific queries over generic category queries. A real
buyer typing "Rado watches Limassol" is closer to a sale than one typing "best
jewellers." Aim for at least 5 product/brand/service-specific queries when the
site provides enough detail.

GROUP B — "Branded" questions ({n_branded} of the {target_count}). USE the
business name. These test what AI already knows about this specific business.
- 1 "comparison": alternatives to {name} in this city
- 1 "legitimacy": is {name} reputable / trustworthy
- 1 "factual_attributes" or "awareness": basic facts (location, hours,
  offerings, history)
- Extra branded slots (if {n_branded} > 3): mix of the same three types

Tag each question with one of these EXACT category strings:
- "category_recommendation" (discovery: "best X in Y" style)
- "problem_solution"        (discovery: "I need X", "looking for X" style)
- "comparison"              (branded: alternatives to the business)
- "legitimacy"              (branded: reputable / trustworthy)
- "factual_attributes"      (branded: location / hours / services / products)
- "awareness"               (branded: tell me about / what is this business)

Rules:
- Every question must read like natural English a real person would type.
- Discovery questions MUST NOT contain "{name}" or any obvious variant.
- Branded questions MUST contain "{name}" verbatim.
- Prefer product/service specifics over generic phrasing when you can infer
  them (e.g. for a jewellery + Swiss-watches store: engagement rings, watch
  service, specific brands the site mentions).
- Vary the phrasing — don't produce five near-identical templates.
- Keep each question under 25 words.

Return JSON EXACTLY like this (no extra keys, no trailing text):
{{"prompts":[{{"text":"...","category":"category_recommendation"}}]}}
"""


def generate_prompts_for_entity(
    *,
    name: str,
    category: str | None,
    city: str | None,
    domain: str | None,
    api_key: str,
    model: str | None = None,
    website_snippet: str | None = None,
    target_count: int = DEFAULT_TARGET_COUNT,
) -> list[GeneratedPrompt]:
    """Call the LLM generator and return validated buyer questions.

    When ``website_snippet`` is provided (extracted homepage text), the LLM
    writes long-tail product/brand queries around what the site actually sells
    — much higher signal than category-only guessing. On any failure raises
    ``PromptGenerationError`` so the caller falls back to the static generator.
    """
    if not api_key:
        raise PromptGenerationError("No OpenRouter key configured")
    if not name.strip():
        raise PromptGenerationError("Business name is required")

    prompt = build_prompt(
        name=name, category=category, city=city, domain=domain,
        website_snippet=website_snippet, target_count=target_count,
    )
    raw = _post_openrouter(prompt=prompt, api_key=api_key, model=model or DEFAULT_MODEL)
    parsed = _parse_response(raw, name=name)

    # Sanity gate: must have at least one no-name discovery and one branded, or
    # the report won't have anything meaningful to compare against.
    has_discovery = any(p.category in {"category_recommendation", "problem_solution"} for p in parsed)
    has_branded = any(p.category in {"comparison", "legitimacy", "factual_attributes", "awareness"} for p in parsed)
    if not (has_discovery and has_branded):
        raise PromptGenerationError(
            f"Generator returned unusable mix (discovery={has_discovery}, branded={has_branded})"
        )
    return parsed


def _post_openrouter(*, prompt: str, api_key: str, model: str) -> str:
    """Single OpenRouter POST with automatic model-fallback + JSON mode."""
    import httpx

    body = {
        "model": model,
        "models": [model, *FALLBACK_MODELS],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.6,  # a little more variety than the classifier (0.2)
    }
    try:
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.environ.get("GR_APP_BASE_URL", "http://localhost:4321"),
                "X-Title": "Visible to AI",
            },
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise PromptGenerationError(f"OpenRouter call failed: {type(exc).__name__}") from exc

    try:
        data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as exc:  # noqa: BLE001
        raise PromptGenerationError(f"Malformed OpenRouter response: {exc}") from exc
    if not content:
        raise PromptGenerationError("Empty content from generator")
    return content[:_MAX_OUTPUT_CHARS]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(raw: str, *, name: str) -> list[GeneratedPrompt]:
    """Parse the generator's JSON. Tolerates markdown fences some models emit,
    and drops rows that violate the discovery/branded contract."""
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PromptGenerationError(f"Invalid JSON: {exc}") from exc
    items = obj.get("prompts") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise PromptGenerationError("JSON missing 'prompts' list")

    lowered_name = name.lower().strip()
    out: list[GeneratedPrompt] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        q = str(row.get("text") or "").strip()
        cat = str(row.get("category") or "").strip()
        if not q or cat not in _VALID_CATEGORIES:
            continue

        # Enforce the discovery/branded invariant: a discovery prompt must NOT
        # contain the brand name (otherwise Share-of-Model is contaminated).
        is_discovery = cat in {"category_recommendation", "problem_solution"}
        has_name = lowered_name in q.lower()
        if is_discovery and has_name:
            logger.info("Dropping generated discovery prompt that contained the brand: %r", q)
            continue
        if not is_discovery and not has_name:
            # Branded categories require the name; a "legitimacy" prompt without
            # the name is useless for hallucination detection.
            logger.info("Dropping branded prompt that omitted the brand: %r", q)
            continue

        out.append(GeneratedPrompt(text=q, category=cat))
    return out


def to_json(items: list[GeneratedPrompt]) -> list[dict]:
    """Serialise for storage on ``BusinessEntity.custom_prompts``."""
    return [{"text": p.text, "category": p.category} for p in items]


def from_json(items: list[dict] | None) -> list[GeneratedPrompt]:
    """Reverse of :func:`to_json`; strict — drops rows that lost their shape."""
    out: list[GeneratedPrompt] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        cat = str(row.get("category") or "").strip()
        if text and cat in _VALID_CATEGORIES:
            out.append(GeneratedPrompt(text=text, category=cat))
    return out
