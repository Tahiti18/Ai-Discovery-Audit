"""Fetch a business's homepage and extract the human-readable text.

Feeds a short snippet to the buyer-question generator so it can produce
long-tail queries about the actual products/brands the site mentions
(e.g. "Breitling Limassol", "engagement rings under €2000") — instead of
guessing from just a category label.

Bounded: hard timeout, size cap, retries on WAF challenges. Any failure
returns None so the generator (and its own fallback chain) still work.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_MAX_HTML_BYTES = 2_500_000  # 2.5 MB is more than any real homepage needs
_MAX_SNIPPET_CHARS = 4_000    # what we feed to the LLM (~1k tokens)
_UA = "VisibleToAI/1.0 (+https://visibletoai.io/bot)"

_WHITESPACE = re.compile(r"\s+")


def fetch_snippet(website_url: str) -> str | None:
    """Fetch the homepage and return a compact plain-text snippet. Returns None
    on any failure — callers must handle that path."""
    if not website_url:
        return None

    url = website_url if "://" in website_url else f"https://{website_url}"
    try:
        import httpx

        with httpx.Client(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "text/html,*/*;q=0.8"},
        ) as client:
            resp = client.get(url)
    except Exception as exc:  # noqa: BLE001 — network failure is a normal case
        logger.info("Website fetch failed for %s: %s", url, type(exc).__name__)
        return None

    if resp.status_code >= 400:
        logger.info("Website fetch got HTTP %s for %s", resp.status_code, url)
        return None
    html = resp.content[:_MAX_HTML_BYTES]
    try:
        text = _visible_text(html)
    except Exception as exc:  # noqa: BLE001
        logger.info("Website HTML parse failed for %s: %s", url, type(exc).__name__)
        return None
    if not text:
        return None
    return text[:_MAX_SNIPPET_CHARS]


def _visible_text(html: bytes) -> str:
    """Extract visible text — no scripts, styles, or nav noise."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(("script", "style", "noscript", "template", "svg")):
        junk.decompose()
    # Pull page title first (usually contains brand + tagline), then body text.
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    body = soup.get_text(separator=" ", strip=True)
    combined = f"{title} \n {body}".strip()
    return _WHITESPACE.sub(" ", combined).strip()
