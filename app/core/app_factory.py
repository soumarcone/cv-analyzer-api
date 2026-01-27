from __future__ import annotations

"""Application factory for FastAPI app.

Centralizes app construction (metadata, middleware, handlers, routers) to
improve testability and separation of concerns compared to a monolithic main.
"""

from fastapi import FastAPI

from app.api.routes import cv_router, health_router
from app.core.config import settings
from app.core.exception_handlers import setup_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_id_middleware
from app.core.openapi import apply_openapi_customizations


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        Configured FastAPI app with middleware, handlers, routers and docs.
    """
    # Logging first so subsequent init logs are formatted as desired
    configure_logging(settings.log)

    app = FastAPI(
        title="CV Analyzer API",
        description=(
            "API para analisar currículos (PDF/DOCX) contra descrições de vagas, "
            "retornando um JSON estruturado: summary, fit_score com justificativa, "
            "strengths, gaps, missing_keywords, rewrite_suggestions, ats_notes, "
            "red_flags e next_steps. Requer X-API-Key e implementa rate limit, logs "
            "seguros e cache por hash."
        ),
        version="0.1.0",
        contact={
            "name": "CV Analyzer",
            "url": "https://github.com/",
        },
        license_info={
            "name": "MIT License",
            "url": "https://opensource.org/licenses/MIT",
        },
    )

    # Middleware
    app.middleware("http")(request_id_middleware)

    # Exception handlers
    setup_exception_handlers(app)

    # Routers
    app.include_router(cv_router, prefix="/v1")
    app.include_router(health_router)

    # OpenAPI customizations (security scheme, tags, exemptions)
    apply_openapi_customizations(app)

    return app
