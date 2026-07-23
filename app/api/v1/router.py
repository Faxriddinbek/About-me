"""Aggregate router for API v1.

Feature routers are attached here in later steps; ``main`` mounts this single
router under ``/api/v1`` so API versioning is controlled in exactly one place.
"""

from fastapi import APIRouter

api_router = APIRouter()
