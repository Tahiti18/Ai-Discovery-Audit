"""Platform configuration loaded from environment variables.

Deliberately dependency-light: a plain settings object backed by ``os.environ``
with sane local-dev defaults. No secrets are hard-coded; production must supply
``GR_JWT_SECRET`` and a real ``GR_DATABASE_URL``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Load platform/.env (gitignored) so local secrets — Stripe keys, the provider
# key, etc. — live in one file instead of being passed on the command line.
# Real environments set these as actual env vars; load_dotenv never overrides
# values already present in the environment.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # noqa: BLE001 — dotenv is a convenience, never required
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the platform API and workers."""

    # ─── Database ────────────────────────────────────────────────────────────
    # Default to a local SQLite file so the foundation is runnable and testable
    # without Postgres. Production sets GR_DATABASE_URL to a postgres+psycopg URL.
    database_url: str = field(
        default_factory=lambda: os.environ.get("GR_DATABASE_URL", "sqlite:///./geoready_platform.db")
    )

    # ─── Cache / broker ──────────────────────────────────────────────────────
    redis_url: str = field(default_factory=lambda: os.environ.get("GR_REDIS_URL", "redis://localhost:6379/0"))

    # ─── Auth ────────────────────────────────────────────────────────────────
    jwt_secret: str = field(default_factory=lambda: os.environ.get("GR_JWT_SECRET", "dev-insecure-change-me"))
    jwt_algorithm: str = field(default_factory=lambda: os.environ.get("GR_JWT_ALG", "HS256"))
    # 14 days by default: this is a consumer magic-link product — a 1-hour
    # session would force a re-login mid-workday. Override per environment.
    jwt_ttl_seconds: int = field(default_factory=lambda: int(os.environ.get("GR_JWT_TTL_SECONDS", str(14 * 24 * 3600))))

    # ─── AI provider keys (slotted now, unused until later phases) ────────────
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    perplexity_api_key: str | None = field(default_factory=lambda: os.environ.get("PERPLEXITY_API_KEY"))

    # ─── Worker execution ────────────────────────────────────────────────────
    # When true, Celery runs tasks inline (no broker needed) — used by tests and
    # by single-process local dev. Production / docker-compose stacks override
    # this to `false` explicitly (see platform/docker-compose.yml) and run a real
    # `celery -A geoready_platform.workers.celery_app worker` against Redis. The
    # default is True so a fresh `uvicorn` + `pip install -e` checkout works
    # end-to-end without requiring the operator to also start Redis + a worker
    # just to see a probe complete; production deployments MUST set this to
    # `false` (the docker-compose, k8s, and prod env templates already do).
    celery_eager: bool = field(default_factory=lambda: _env_bool("GR_CELERY_EAGER", True))
    # In eager local dev, run the (synchronous) job on a background thread so the
    # enqueue POST returns 202 immediately and the client polls — instead of the
    # request blocking for the entire multi-prompt probe. Tests set this false to
    # keep deterministic inline completion.
    probe_eager_background: bool = field(default_factory=lambda: _env_bool("GR_PROBE_EAGER_BACKGROUND", True))
    audit_timeout_seconds: int = field(default_factory=lambda: int(os.environ.get("GR_AUDIT_TIMEOUT_SECONDS", "60")))

    # ─── Rate limiting (per API key) ─────────────────────────────────────────
    free_audits_per_day: int = field(default_factory=lambda: int(os.environ.get("GR_FREE_AUDITS_PER_DAY", "5")))
    free_probes_per_day: int = field(default_factory=lambda: int(os.environ.get("GR_FREE_PROBES_PER_DAY", "3")))

    # ─── Ownership verification gate ─────────────────────────────────────────
    # When True, audit enqueue refuses entities whose `verified_at` is null and
    # the worker re-asserts the same check defense-in-depth. When False (the
    # default), audits run on any entity owned by the caller's org — auth +
    # quota only, the same posture probes already use. DB columns, `/verify`
    # endpoints, and the ownership service are kept intact so the gate can be
    # re-enabled by flipping this flag without a code change.
    require_ownership_verification: bool = field(
        default_factory=lambda: _env_bool("GR_REQUIRE_OWNERSHIP_VERIFICATION", False)
    )

    # ─── Perception probe ────────────────────────────────────────────────────
    # 15 gives room for a proper matrix view of AI visibility: broad category
    # queries + long-tail product/brand queries + branded checks. Costs ~$0.05
    # per audit via OpenRouter (~$0.001 each). Override with GR_PROBE_MAX_PROMPTS.
    probe_max_prompts: int = field(default_factory=lambda: int(os.environ.get("GR_PROBE_MAX_PROMPTS", "15")))
    probe_provider: str | None = field(default_factory=lambda: os.environ.get("GR_PROBE_PROVIDER"))

    # ─── Billing (Stripe) ────────────────────────────────────────────────────
    # All read from env; empty in dev until real keys are pasted in. When the
    # secret key is unset, billing endpoints return a clear "not configured"
    # error instead of crashing. Prices are Stripe price IDs (price_...).
    stripe_secret_key: str | None = field(default_factory=lambda: os.environ.get("STRIPE_SECRET_KEY"))
    stripe_publishable_key: str | None = field(default_factory=lambda: os.environ.get("STRIPE_PUBLISHABLE_KEY"))
    stripe_webhook_secret: str | None = field(default_factory=lambda: os.environ.get("STRIPE_WEBHOOK_SECRET"))
    stripe_price_pro: str | None = field(default_factory=lambda: os.environ.get("STRIPE_PRICE_PRO"))
    stripe_price_founding: str | None = field(default_factory=lambda: os.environ.get("STRIPE_PRICE_FOUNDING"))
    stripe_price_business: str | None = field(default_factory=lambda: os.environ.get("STRIPE_PRICE_BUSINESS"))

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    # ─── Auth / magic-link ───────────────────────────────────────────────────
    # Base URL of the frontend, used to build the sign-in link in magic-link
    # emails. Locally this is the Astro dev server; production sets it to the
    # real domain (e.g. https://visibletoai.io).
    app_base_url: str = field(default_factory=lambda: os.environ.get("GR_APP_BASE_URL", "http://localhost:4321"))
    # Transactional email via Resend. Setting RESEND_API_KEY turns real emails
    # on (overridable with GR_EMAIL_ENABLED=false). With no key and no explicit
    # flag, dev mode returns the sign-in link on-page instead (localhost only).
    resend_api_key: str | None = field(default_factory=lambda: os.environ.get("RESEND_API_KEY"))
    email_from: str = field(
        default_factory=lambda: os.environ.get("GR_EMAIL_FROM", "Visible to AI <signin@visibletoai.io>")
    )
    email_enabled: bool = field(
        default_factory=lambda: _env_bool("GR_EMAIL_ENABLED", bool(os.environ.get("RESEND_API_KEY")))
    )

    # Comma-separated emails auto-granted the internal "owner" plan on every
    # sign-in (unlimited businesses/checks, all features). For the product
    # owner/staff — never a sales path. Case-insensitive.
    comped_emails: frozenset[str] = field(
        default_factory=lambda: frozenset(
            e.strip().lower() for e in os.environ.get("GR_COMPED_EMAILS", "").split(",") if e.strip()
        )
    )

    @property
    def auth_dev_links_enabled(self) -> bool:
        """Whether /v1/auth/request may echo the sign-in link in the response.

        SECURITY: echoing the link lets anyone who can reach the API sign in as
        any email — acceptable ONLY on a local machine. Auto-enabled when the
        app base URL is localhost; anywhere else it must be forced explicitly
        with GR_AUTH_DEV_LINKS=true (don't)."""
        if _env_bool("GR_AUTH_DEV_LINKS", False):
            return True
        host = self.app_base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        return host in ("localhost", "127.0.0.1", "[::1]")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres", "postgresql"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
