from __future__ import annotations

from app.api.routes.cv import router as cv_router
from app.api.routes.health import router as health_router

__all__ = ["cv_router", "health_router"]
