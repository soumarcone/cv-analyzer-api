from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict:
    """Health check endpoint.

    Returns a simple status response to verify the API is operational.
    Used by load balancers and monitoring systems to determine service health.

    Returns:
        dict: A dictionary with a single "status" key set to "ok".
    """

    return {"status": "ok"}
