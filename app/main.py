from fastapi import FastAPI

from app.api.routes import cv_router, health_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import request_id_middleware

configure_logging(settings.log)

app = FastAPI(title="CV Analyzer API")
app.middleware("http")(request_id_middleware)

app.include_router(cv_router, prefix="/v1")
app.include_router(health_router)