"""Detect wrong facts AI is publishing about a business.

Called after the probe finishes. Reads all 15 answers + the business's real
homepage snippet, and asks an LLM to find every factual error AI is stating.

Turns "AI mentions you 25% of the time" into "AI mentions you 25% of the time
AND is saying 3 specific things about you that are wrong — here's how to fix
each one." That's the actual consulting deliverable.

Design contract:
- Pure over inputs — no DB access, no globals.
- Bounded cost: one HTTP call, hard timeout, model fallback via OpenRouter.
- Never crashes a probe run: on any failure raises MisinformationError; caller
  logs and moves on with an empty list.
- Only outputs errors with confidence >= 0.7 to keep credibility high.
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

_VALID_ISSUE_TYPES = {
    "wrong_brand",     # AI names a brand/product the business doesn't carry
    "wrong_website",   # AI links to a different domain
    "wrong_service",   # AI credits/omits a service they do/don't provide
    "wrong_location",  # AI states wrong address/city/region
    "wrong_status",    # AI says closed / online-only when they aren't
    "wrong_contact",   # wrong phone / hours / email
    "wrong_history",   # wrong founding year, ownership, etc.
    "other",           # catch-all for edge cases
}

_VALID_SEVERITY = {"high", "medium", "low"}


class MisinformationError(Exception):
    """Raised when detection fails; caller logs and moves on."""


@dataclass(frozen=True)
class MisinformationFinding:
    """One factual error AI is publishing about the business."""

    issue_type: str
    severity: str          # "high" | "medium" | "low"
    description: str       # one-sentence naming what's wrong
    evidence: str          # exact quote from an AI answer
    fix: str               # concrete action the business should take
    confidence: float


_SYSTEM_PROMPT = """\
You are a fact-checker for a business's AI visibility. Given the business's
current homepage AND recent AI answers about them, identify every fact AI is
stating that appears WRONG compared to the actual homepage.

Return valid JSON only — no markdown, no prose outside the JSON.
"""


def build_prompt(
    *,
    name: str,
    domain: str | None,
    website_snippet: str | None,
    answers: list[str],  # raw AI answer texts (from brand-check questions especially)
) -> str:
    """Produce the user prompt for the detector. Pure — testable."""
    homepage_block = website_snippet or "(homepage content not available)"
    joined = "\n\n---\n\n".join(a for a in answers if a and a.strip()) or "(no answers)"

    return f"""\
Business: {name}
Domain: {domain or 'unknown'}

Homepage content (source of truth):
---
{homepage_block[:4000]}
---

AI answers about this business:
---
{joined[:8000]}
---

TASK: For every FACT AI stated that is WRONG according to the homepage above,
produce one entry. Focus on:

1. **wrong_brand** — AI says they carry a brand/product not in the homepage
   (or omits a major one that IS in the homepage). Example: AI says they
   carry Chopard but homepage doesn't list Chopard.
2. **wrong_website** — AI links to a different domain. Example: AI says the
   website is era-jewellers.com but the actual domain is eramorethangold.com.
3. **wrong_service** — AI credits them with a service they don't offer
   (or omits a service they do offer) — repair, appraisal, online shop, etc.
4. **wrong_location** — AI states wrong address, city, or calls the wrong
   location their "main store".
5. **wrong_status** — AI says they're closed / online-only when the homepage
   shows they're open and physical.
6. **wrong_contact** — wrong phone / hours / email.
7. **wrong_history** — wrong founding year, ownership, etc.
8. **other** — anything else clearly contradicted by the homepage.

Rules:
- Base every finding on evidence from BOTH the homepage AND an AI answer.
- The `evidence` field must be a direct quote from an AI answer.
- If AI states something that isn't mentioned on the homepage but isn't clearly
  contradicted (silence != wrong), DON'T flag it.
- Confidence < 0.7 → don't include the row.
- Return top 10 findings by severity (high first, then medium, then low).
- Skip minor prose disagreements — focus on customer-impact facts.

Return JSON EXACTLY like this (no extra keys, no trailing text):
{{"findings":[{{"issue_type":"wrong_brand","severity":"high","description":"...","evidence":"...","fix":"...","confidence":0.9}}]}}
"""


def detect_misinformation(
    *,
    name: str,
    domain: str | None,
    website_snippet: str | None,
    answers: list[str],
    api_key: str,
    model: str | None = None,
) -> list[MisinformationFinding]:
    """Call the LLM detector and return validated findings.

    Raises ``MisinformationError`` on any failure. The classifier needs both
    a homepage snippet AND at least one answer to compare — without either, it
    would hallucinate its own findings, so we refuse.
    """
    if not api_key:
        raise MisinformationError("No OpenRouter key configured")
    if not (website_snippet and website_snippet.strip()):
        raise MisinformationError("Homepage snippet required — nothing to fact-check against")
    if not any(a and a.strip() for a in answers):
        raise MisinformationError("At least one AI answer required")

    prompt = build_prompt(
        name=name, domain=domain, website_snippet=website_snippet, answers=answers,
    )
    raw = _post_openrouter(prompt=prompt, api_key=api_key, model=model or DEFAULT_MODEL)
    return _parse_response(raw)


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
        "temperature": 0.2,  # bounded — this is fact-checking, not writing
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
        raise MisinformationError(f"OpenRouter call failed: {type(exc).__name__}") from exc

    try:
        data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as exc:  # noqa: BLE001
        raise MisinformationError(f"Malformed OpenRouter response: {exc}") from exc
    if not content:
        raise MisinformationError("Empty content from detector")
    return content[:_MAX_OUTPUT_CHARS]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(raw: str) -> list[MisinformationFinding]:
    """Parse the detector's JSON. Tolerates markdown fences some models emit."""
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MisinformationError(f"Invalid JSON: {exc}") from exc
    items = obj.get("findings") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise MisinformationError("JSON missing 'findings' list")

    out: list[MisinformationFinding] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        issue_type = str(row.get("issue_type") or "").strip().lower()
        severity = str(row.get("severity") or "").strip().lower()
        description = str(row.get("description") or "").strip()
        evidence = str(row.get("evidence") or "").strip()
        fix = str(row.get("fix") or "").strip()
        if issue_type not in _VALID_ISSUE_TYPES or severity not in _VALID_SEVERITY:
            continue
        if not (description and fix):
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.7:
            continue
        out.append(MisinformationFinding(
            issue_type=issue_type,
            severity=severity,
            description=description[:280],
            evidence=evidence[:600],
            fix=fix[:280],
            confidence=confidence,
        ))
    # High severity first, then medium, then low.
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda f: (order.get(f.severity, 9), -f.confidence))[:10]


def to_json(findings: list[MisinformationFinding]) -> list[dict]:
    """Serialise for storage on ``ProbeRun.flags`` (under a source marker)."""
    return [
        {
            "source": "llm_misinformation",
            "issue_type": f.issue_type,
            "severity": f.severity,
            "description": f.description,
            "evidence": f.evidence,
            "fix": f.fix,
            "confidence": f.confidence,
        }
        for f in findings
    ]
