"""FastAPI application factory for the platform API.

Mounted independently from the OSS ``geo_optimizer.web`` demo. Structured
logging is configured with request/org/entity context; raw crawled HTML and
credentials are never logged.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from geoready_platform import __version__
from geoready_platform.api.routers import audits, entities, health, orgs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="GeoReady AI Visibility Platform API",
        version=__version__,
        description="Phase 0 foundation: orgs, entities, ownership verification, audit-as-signal jobs.",
    )
    app.include_router(health.router)
    app.include_router(orgs.router)
    app.include_router(entities.router)
    app.include_router(audits.router)
    return app


app = create_app()
