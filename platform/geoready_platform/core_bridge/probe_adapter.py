"""Probe adapter: the only probe code that touches the engine / LLM providers.

Provider resolution order (first available wins):
1. **OpenRouter** (OPENROUTER_API_KEY) — one key, 400+ models incl. Perplexity,
   OpenAI, Anthropic, Google. Default model GR_PROBE_MODEL or "perplexity/sonar"
   (web-grounded → returns citations → competitor extraction works).
2. The engine's own resolver (Perplexity / OpenAI / Anthropic / Groq direct).

Per-prompt provenance (provider, model, citations) is preserved either way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_OPENROUTER_MODEL = "perplexity/sonar"  # web-grounded → citations
_TIMEOUT = 40        # overall read budget per prompt
_CONNECT_TIMEOUT = 10  # fail fast if the provider host can't be reached


@dataclass
class ProbeResponse:
    """Normalized single-prompt probe response with provenance."""

    prompt: str
    provider: str
    model: str
    text: str
    citations: list[str] = field(default_factory=list)
    error: str | None = None


def _openrouter_model() -> str:
    return os.environ.get("GR_PROBE_MODEL") or _DEFAULT_OPENROUTER_MODEL


def resolve_probe_provider(provider: str | None = None) -> tuple[str | None, str | None]:
    """Return (provider, api_key). Prefer OpenRouter when its key is set."""
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key and not provider:
        return "openrouter", or_key
    if provider == "openrouter":
        return ("openrouter", or_key) if or_key else ("openrouter", None)
    from geo_optimizer.core.citations import resolve_provider

    return resolve_provider(provider)


def _extract_citations(data: dict, message: dict) -> list[str]:
    citations: list[str] = list(data.get("citations") or [])
    for ann in message.get("annotations") or []:
        url = (ann.get("url_citation") or {}).get("url") if isinstance(ann, dict) else None
        if url and url not in citations:
            citations.append(url)
    for sr in data.get("search_results") or []:
        url = sr.get("url") if isinstance(sr, dict) else None
        if url and url not in citations:
            citations.append(url)
    return citations


def _run_openrouter(prompt: str, *, api_key: str) -> ProbeResponse:
    import httpx

    model = _openrouter_model()
    try:
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=httpx.Timeout(_TIMEOUT, connect=_CONNECT_TIMEOUT),
        )
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return ProbeResponse(
            prompt=prompt,
            provider="openrouter",
            model=data.get("model", model),
            text=message.get("content") or "",
            citations=_extract_citations(data, message),
        )
    except Exception as exc:  # noqa: BLE001 — never leak the key; report type/message
        return ProbeResponse(prompt=prompt, provider="openrouter", model=model, text="",
                             error=f"{type(exc).__name__}: {exc}")


def run_prompt(prompt: str, *, provider: str, api_key: str) -> ProbeResponse:
    """Query one prompt against the resolved provider and normalize the response."""
    if provider == "openrouter":
        return _run_openrouter(prompt, api_key=api_key)

    from geo_optimizer.core.llm_client import query_llm

    resp = query_llm(prompt, provider=provider, api_key=api_key)
    return ProbeResponse(
        prompt=prompt,
        provider=resp.provider or provider,
        model=resp.model or "",
        text=resp.text or "",
        citations=list(resp.citations or []),
        error=resp.error,
    )
