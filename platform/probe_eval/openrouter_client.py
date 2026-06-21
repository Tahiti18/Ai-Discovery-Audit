"""Minimal OpenRouter client — EVAL TOOLING ONLY.

Not part of the product and not a provider abstraction. It exists so the
evaluation harness can record real responses for live testing. OpenRouter is
OpenAI-compatible, so this is a single chat-completions POST.

SECURITY: the API key is read from OPENROUTER_API_KEY at call time and used only
in the Authorization header. It is never printed, logged, returned, or written
to any fixture. Do not change that.
"""

from __future__ import annotations

import os

from geoready_platform.core_bridge.probe_adapter import ProbeResponse

_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 60


def available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


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


def run_prompt(prompt: str, *, model: str, timeout: float = _TIMEOUT) -> ProbeResponse:
    """Query OpenRouter for one prompt. Returns a ProbeResponse (provenance kept).

    ``timeout`` is the total request timeout in seconds; on expiry a clear
    error is returned (never hangs).
    """
    import httpx

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return ProbeResponse(prompt=prompt, provider="openrouter", model=model, text="",
                             error="OPENROUTER_API_KEY not set")
    try:
        resp = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=httpx.Timeout(timeout),
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
    except Exception as exc:  # noqa: BLE001 — never leak key; report type/message only
        # Defensive: ensure no header/key is in the message.
        msg = f"{type(exc).__name__}: {exc}"
        return ProbeResponse(prompt=prompt, provider="openrouter", model=model, text="", error=msg)
