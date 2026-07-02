"""Transactional email via Resend's HTTP API.

Deliberately tiny: one provider, one template, no SDK dependency (plain httpx).
Used only when settings.email_enabled (i.e. RESEND_API_KEY is configured).
Raises EmailSendError on any failure so callers can respond honestly instead of
pretending an email went out.
"""

from __future__ import annotations

import logging

import httpx

from geoready_platform.config import get_settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


class EmailSendError(Exception):
    pass


def send_magic_link(*, to: str, login_url: str) -> None:
    """Send the sign-in link email. Raises EmailSendError on failure."""
    settings = get_settings()
    if not settings.resend_api_key:
        raise EmailSendError("No email backend configured (RESEND_API_KEY is unset).")

    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;padding:24px 8px;color:#1a1a1a">
  <h2 style="font-weight:600;margin:0 0 8px">Sign in to Visible to AI</h2>
  <p style="color:#555;line-height:1.6;margin:0 0 20px">
    Click the button below to sign in. This link works once and expires in 15 minutes.
  </p>
  <a href="{login_url}"
     style="display:inline-block;background:#8B5CF6;color:#fff;text-decoration:none;
            padding:12px 22px;border-radius:10px;font-weight:600">Sign in →</a>
  <p style="color:#999;font-size:12px;line-height:1.6;margin:24px 0 0">
    If you didn't request this, you can safely ignore this email — nobody can
    sign in without clicking the link.
  </p>
</div>"""

    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": "Your sign-in link for Visible to AI",
                "html": html,
            },
            timeout=10.0,
        )
        if resp.status_code >= 400:
            # Never log the recipient's token/link; status + provider error only.
            logger.error("Resend rejected the email: HTTP %s %s", resp.status_code, resp.text[:300])
            raise EmailSendError("The email service rejected the message.")
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", exc)
        raise EmailSendError("Could not reach the email service.") from exc
