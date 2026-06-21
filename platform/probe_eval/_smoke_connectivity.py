r"""Tiny OpenRouter connectivity test — EVAL TOOLING ONLY.

One business, one prompt, 20s timeout, flushed progress messages, graceful
failure. Writes NO fixtures and prints NO secrets. Use this to confirm the live
path works before any larger run.

Run from repo root:
    $env:PYTHONPATH = "$PWD\platform;$PWD\src"
    python -m probe_eval._smoke_connectivity
"""

from __future__ import annotations

import sys

from geoready_platform.services.probe import prompt_generator

from probe_eval import openrouter_client
from probe_eval.harness import business_by_id

# Fast, cheap, non-web model to isolate connectivity (not citation quality).
MODEL = "openai/gpt-4o-mini"
BUSINESS_ID = "slack"
TIMEOUT_SECONDS = 20.0


def _say(msg: str) -> None:
    print(msg, flush=True)  # flush so progress shows even if the call stalls


def main() -> int:
    _say("starting OpenRouter test")

    if not openrouter_client.available():
        _say("ERROR: OPENROUTER_API_KEY is not set in this process environment.")
        return 2

    _say(f"selected model: {MODEL}")

    biz = business_by_id(BUSINESS_ID)
    if biz is None:
        _say(f"ERROR: business '{BUSINESS_ID}' not found in benchmark.")
        return 2
    _say(f"selected business: {biz['name']} ({biz.get('category')}, {biz.get('city')})")

    prompts = prompt_generator.generate_prompts(
        name=biz["name"], category=biz.get("category"), city=biz.get("city"), max_prompts=1
    )
    if not prompts:
        _say("ERROR: no prompt generated.")
        return 2
    prompt = prompts[0].text
    _say(f"selected prompt: {prompt}")

    _say(f"request sent (timeout {int(TIMEOUT_SECONDS)}s)...")
    resp = openrouter_client.run_prompt(prompt, model=MODEL, timeout=TIMEOUT_SECONDS)

    if resp.error:
        _say(f"ERROR: {resp.error}")
        return 1

    preview = (resp.text or "").strip().replace("\n", " ")
    if len(preview) > 160:
        preview = preview[:160] + "..."
    _say("response received")
    _say(f"  model returned: {resp.model}")
    _say(f"  text length: {len(resp.text or '')} chars")
    _say(f"  citations: {len(resp.citations)}")
    _say(f"  preview: {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
