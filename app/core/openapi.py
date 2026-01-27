"""OpenAPI metadata and customization utilities.

Provides a helper to enrich the generated OpenAPI schema with:
- API metadata (description, version, contact, license)
- Tags metadata
- API Key security scheme (``X-API-Key``) with per-path overrides

This keeps documentation concerns decoupled from the app factory.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI


def apply_openapi_customizations(app: FastAPI) -> None:
    """Patch FastAPI's OpenAPI generation to add metadata and security.

    - Injects components.securitySchemes for API Key auth (header ``X-API-Key``)
    - Marks all operations as requiring API Key by default, then exempts health
      endpoints by setting ``security: []``
    - Adds tags metadata if not present
    """

    original_openapi = app.openapi

    def custom_openapi() -> Dict[str, Any]:
        schema = original_openapi()

        # Components / security scheme
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes.setdefault(
            "ApiKeyAuth",
            {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Provide your API key via the X-API-Key header.",
            },
        )

        # Global security requirement (applies to all operations)
        schema.setdefault("security", [{"ApiKeyAuth": []}])

        # Tags metadata
        tags = schema.setdefault("tags", [])
        existing_tag_names = {t.get("name") for t in tags}
        desired_tags = [
            {
                "name": "CV",
                "description": "Endpoints for CV parsing and analysis.",
            },
            {
                "name": "Health",
                "description": "Liveness and readiness checks.",
            },
        ]
        for tag in desired_tags:
            if tag["name"] not in existing_tag_names:
                tags.append(tag)

        # Exempt health endpoints from auth by setting security: []
        paths = schema.get("paths", {})
        for path, methods in paths.items():
            if path.endswith("/health"):
                for method_obj in methods.values():
                    if isinstance(method_obj, dict):
                        method_obj["security"] = []

        return schema

    app.openapi = custom_openapi  # type: ignore[assignment]
