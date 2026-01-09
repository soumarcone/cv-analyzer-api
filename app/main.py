from fastapi import FastAPI
from app.api.routes import router as api_router

app = FastAPI(title="CV Analyzer API")

app.include_router(api_router, prefix="/v1")


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint.
    
    Returns:
        dict: Status response indicating API is operational.
    """
    return {"status": "ok"}