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
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
FALLBACK_MODELS = ("anthropic/claude-sonnet-4.5",)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 20.0
_MAX_OUTPUT_CHARS = 10_000

_VALID_ISSUE_TYPES = {
    # ── Original: contradictions against the homepage ─────────────────────────
    "wrong_brand",         # AI names a brand/product the business doesn't carry
    "wrong_website",       # AI links to a different domain
    "wrong_service",       # AI credits/omits a service they do/don't provide
    "wrong_location",      # AI states wrong address / city / main-store claim
    "wrong_status",        # AI says closed / online-only when they aren't
    "wrong_contact",       # wrong phone / hours / email
    "wrong_history",       # wrong founding year, ownership, etc.
    # ── Coverage expansion (catch positive-sounding hallucinations) ───────────
    "wrong_relationship",  # "sister store", "same company as X", "part of Y group"
    "wrong_person",        # invented staff/owner names ("owner Alyssa" when owner is Kyriakos)
    "wrong_credentials",   # unsubstantiated "official/authorised/certified" dealer status
    "wrong_ratings",       # suspiciously precise numbers ("100% rating from 18 reviews")
    "name_confusion",      # AI conflates the business with a similarly-named unrelated one
    "other",               # catch-all for edge cases
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

Homepage content (source of truth for what the business ACTUALLY offers):
---
{homepage_block[:4000]}
---

AI answers about this business:
---
{joined[:8000]}
---

TASK: Find every FACT AI stated about "{name}" that appears WRONG, INVENTED,
or UNSUPPORTED. Include claims that sound POSITIVE — those are the ones that
mislead the customer the most, and the ones AI most often fabricates.

Issue categories (use exactly these strings):

1. **wrong_brand** — AI says they carry a brand/product not on the homepage.
   Example: AI says "official Chopard dealer" but homepage doesn't list Chopard.

2. **wrong_website** — AI publishes a different domain than the actual one.
   Example: AI cites era-jewellers.com when the actual domain is eramorethangold.com.

3. **wrong_service** — AI credits them with a service they don't offer, OR
   omits a service they explicitly DO offer.

4. **wrong_location** — Wrong address, wrong city, wrong "main store" claim.
   Example: AI calls Paphos the "main store" when homepage shows Limassol.

5. **wrong_status** — Closed/online-only when they aren't (or vice versa).

6. **wrong_contact** — Wrong phone, wrong hours, wrong email.

7. **wrong_history** — Wrong founding year, wrong ownership, wrong tenure.

8. **wrong_relationship** — AI invents a relationship to another business.
   Watch for phrases: "operated by the same company as", "sister store of",
   "part of the X group", "flagship location of", "owned by X".
   Example: AI says "ERA Department Store is operated by the same company as
   ERA More Than Gold" — flag as wrong_relationship unless the homepage
   explicitly confirms the relationship.

9. **wrong_person** — AI names the wrong owner, founder, or staff.
   Example: AI says "owner Alyssa" but homepage lists a different owner.

10. **wrong_credentials** — Unsubstantiated "official / authorised / certified /
    exclusive" dealer or partner status. Watch for words like "official
    retailer", "authorised dealer", "certified partner", "exclusive
    distributor". If the homepage doesn't confirm the exact credential, FLAG IT.

11. **wrong_ratings** — Suspiciously precise ratings or review counts that
    AI could have fabricated. Watch for "100% recommendation rate", "5-star
    average", "X reviews", specific award names.

12. **name_confusion** — AI conflates "{name}" with a different business that
    shares part of its name (e.g. "ERA" prefix, "Jewellers" suffix). Watch for
    AI describing a business with a similar name and treating it as this one.
    Example: AI mentions "ERA Department Store" and treats it as related to
    "{name}" — flag as name_confusion.

13. **other** — anything else clearly false or unsupported.

CRITICAL rules:
- **Positive-sounding claims are still wrong if unsupported.** "Official Rolex
  dealer" and "100% customer rating" sound good — but if the homepage doesn't
  say them, they mislead customers walking through the door expecting it.
- Silence on the homepage is NOT wrong on its own — but INVENTED SPECIFICS
  (specific numbers, specific relationships, specific award names, specific
  people) ARE flag-worthy even if the homepage doesn't explicitly refute them.
- The `evidence` field MUST be a direct quote from an AI answer.
- Confidence < 0.7 → don't include the row.
- Return the top 10 findings by severity (high first).
- Skip minor prose disagreements — focus on things a walk-in customer would
  be misled about.
- The `fix` MUST be a specific, actionable step (update GBP, add schema,
  publish canonical, contact reviewers, etc.).

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

    # Strip parenthetical labels (e.g. "(new site)") from the name before it
    # goes into the fact-checker prompt — same reason as prompt_extraction.
    from geoready_platform.services.probe.prompt_extraction import _strip_labels
    clean_name = _strip_labels(name)
    prompt = build_prompt(
        name=clean_name, domain=domain, website_snippet=website_snippet, answers=answers,
    )
    raw = _post_openrouter(prompt=prompt, api_key=api_key, model=model or DEFAULT_MODEL)
    findings = _parse_response(raw)
    # Post-process: any wrong_website finding whose URL actually redirects to
    # the canonical domain gets downgraded — the traffic still lands correctly.
    return _verify_redirects(findings, canonical_domain=domain)


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


# Any http(s) URL. Stopping at whitespace, quotes, angle brackets and parens
# — good enough for LLM prose evidence; not a general RFC-3986 parser.
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.IGNORECASE)


def _normalize_host(host: str) -> str:
    """Strip scheme, `www.`, and trailing paths so two hosts can be compared."""
    h = host.lower().strip()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0]
    return h[4:] if h.startswith("www.") else h


def _verify_redirects(
    findings: list[MisinformationFinding], *, canonical_domain: str | None
) -> list[MisinformationFinding]:
    """For each ``wrong_website`` finding, follow any URL in the evidence with a
    HEAD request. If it lands on the canonical domain, the redirect is doing
    its job — downgrade severity to ``low`` and rewrite the fix so the report
    doesn't cry wolf.

    Never raises: HEAD failures are treated as "couldn't verify, keep the
    LLM's original severity." Timeout is short and hard-capped."""
    if not canonical_domain or not findings:
        return findings
    canonical = _normalize_host(canonical_domain)
    if not canonical:
        return findings

    import httpx

    updated: list[MisinformationFinding] = []
    for f in findings:
        if f.issue_type != "wrong_website" or f.severity == "low":
            updated.append(f)
            continue

        redirected_ok = False
        for candidate in _URL_PATTERN.findall(f.evidence)[:2]:  # cap to 2 to bound work
            # Only https targets — refuse http:// to avoid mixed-content signals
            # and refuse anything that looks like an attempt to break out.
            if not candidate.lower().startswith("https://"):
                continue
            try:
                with httpx.Client(
                    timeout=8.0, follow_redirects=True,
                    headers={"User-Agent": "VisibleToAI/1.0 (+https://visibletoai.io/bot)"},
                ) as client:
                    # HEAD first (fast, no body); some sites 405 on HEAD → fall back to GET.
                    resp = client.head(candidate)
                    if resp.status_code >= 400:
                        resp = client.get(candidate)
                final_host = _normalize_host(str(resp.url))
                if final_host == canonical:
                    redirected_ok = True
                    break
            except Exception:  # noqa: BLE001 — network failure = "can't verify, keep as-is"
                continue

        if redirected_ok:
            logger.info(
                "Misinformation: wrong_website %r redirects to canonical — downgraded",
                candidate,
            )
            updated.append(replace(
                f,
                severity="low",
                description=(
                    f.description
                    + " (Traffic redirects correctly to your current domain, so nothing is being lost — but AI is still publishing an outdated URL identity.)"
                )[:280],
                fix=(
                    "The redirect is doing its job — no urgent action. To help AI "
                    "learn your canonical URL faster: add sameAs links in your "
                    "Organization schema, update your Google Business Profile, "
                    "and ask any citation you control to update the link."
                )[:280],
            ))
        else:
            updated.append(f)

    return updated


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
