"""FastAPI application factory for the platform API.

Mounted independently from the OSS ``geo_optimizer.web`` demo. Structured
logging is configured with request/org/entity context; raw crawled HTML and
credentials are never logged.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from geoready_platform import __version__
from geoready_platform.api.routers import audits, auth, billing, entities, health, orgs, probe

# Local dev: allow the frontend origin to call the API directly. Auth is via the
# X-API-Key header (not cookies), so "*" is safe here; override in production via
# GR_CORS_ORIGINS (comma-separated). No credentials/cookies are used.
_CORS_ORIGINS = [o.strip() for o in os.environ.get("GR_CORS_ORIGINS", "*").split(",") if o.strip()]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="GeoReady AI Visibility Platform API",
        version=__version__,
        description=(
            "Orgs, entities, ownership verification, audit-as-signal jobs (Phase 0), "
            "and the AI Perception Probe (Phase 1)."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(entities.router)
    app.include_router(audits.router)
    app.include_router(probe.router)
    app.include_router(billing.router)

    @app.get("/")
    def root():
        return {
            "name": "Visible to AI — Platform API",
            "status": "ok",
            "health": "/healthz",
            "docs": "/docs"
        }

    @app.on_event("startup")
    def _refuse_insecure_production() -> None:
        # Fail fast rather than run a public deployment with the dev JWT secret
        # (every session token would be forgeable). Localhost keeps the default.
        from geoready_platform.config import get_settings

        settings = get_settings()
        host = settings.app_base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        is_local = host in ("localhost", "127.0.0.1", "[::1]")
        if not is_local and settings.jwt_secret == "dev-insecure-change-me":
            raise RuntimeError(
                "Refusing to start: GR_APP_BASE_URL is non-local but GR_JWT_SECRET "
                "is still the dev default. Set a strong GR_JWT_SECRET."
            )

    @app.on_event("startup")
    def _reap_stale_runs_on_startup() -> None:
        # A restart almost always means any in-flight probe died with the old
        # process. Mark those orphans failed up front so they never appear active.
        from geoready_platform.db.base import session_scope
        from geoready_platform.services.probe.runner import reap_stale_runs

        try:
            with session_scope() as session:
                n = reap_stale_runs(session)
            if n:
                logging.getLogger(__name__).info("Reaped %s stale probe run(s) on startup", n)
        except Exception:  # noqa: BLE001 — never block startup on cleanup
            logging.getLogger(__name__).warning("Stale-run reap on startup failed", exc_info=True)

    return app


app = create_app()

