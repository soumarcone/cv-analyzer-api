"""Rate limiting adapters.

This package provides a small abstraction layer so the MVP can start with an
in-memory limiter and later migrate to Redis or another shared store without
changing the API layer.
"""
