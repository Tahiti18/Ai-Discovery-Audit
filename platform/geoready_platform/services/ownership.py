"""Domain ownership verification — the hard gate before any crawl or fix.

Two methods, both proving control of the domain:
- **DNS**: a TXT record at ``_geoready.<domain>`` containing the token.
- **File**: ``https://<domain>/.well-known/geoready-verification.txt`` whose
  body contains the token.

All HTTP goes through the engine's anti-SSRF ``fetch_url``; URL safety is checked
with ``validate_public_url``. No bypass for unverified entities exists anywhere
in the platform — the worker re-asserts verification before running an audit.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

WELL_KNOWN_PATH = "/.well-known/geoready-verification.txt"
DNS_RECORD_PREFIX = "_geoready"
TOKEN_PREFIX = "geoready-verification="


def generate_verification_token() -> str:
    return secrets.token_urlsafe(24)


def _domain_of(website_url: str) -> str:
    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    return (parsed.netloc or parsed.path).split(":")[0].lower().strip("/")


def verify_via_file(website_url: str, token: str) -> tuple[bool, str | None]:
    """Fetch the well-known file and check it contains the token."""
    from geo_optimizer.utils.http import fetch_url

    domain = _domain_of(website_url)
    if not domain:
        return False, "Could not determine domain from website_url"

    target = f"https://{domain}{WELL_KNOWN_PATH}"
    response, err = fetch_url(target, timeout=10)
    if err or response is None:
        return False, f"Could not fetch {WELL_KNOWN_PATH}: {err or 'no response'}"
    if response.status_code != 200:
        return False, f"{WELL_KNOWN_PATH} returned HTTP {response.status_code}"

    body = (response.text or "").strip()
    if token in body:
        return True, None
    return False, "Verification file did not contain the expected token"


def verify_via_dns(website_url: str, token: str) -> tuple[bool, str | None]:
    """Look up the TXT record and check it contains the token."""
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        return False, "DNS verification requires the 'dnspython' dependency"

    domain = _domain_of(website_url)
    if not domain:
        return False, "Could not determine domain from website_url"

    record_name = f"{DNS_RECORD_PREFIX}.{domain}"
    try:
        answers = dns.resolver.resolve(record_name, "TXT")
    except Exception as exc:  # noqa: BLE001 — resolver raises many subclasses
        return False, f"DNS lookup failed for {record_name}: {exc}"

    expected = f"{TOKEN_PREFIX}{token}"
    for rdata in answers:
        txt = b"".join(getattr(rdata, "strings", [])).decode("utf-8", "ignore") or str(rdata).strip('"')
        if expected in txt or token in txt:
            return True, None
    return False, "No matching TXT record found"


def verify(website_url: str, token: str, method: str) -> tuple[bool, str | None]:
    """Dispatch to the chosen verification method."""
    if method == "dns":
        return verify_via_dns(website_url, token)
    if method == "file":
        return verify_via_file(website_url, token)
    return False, f"Unknown verification method: {method!r} (expected 'dns' or 'file')"
