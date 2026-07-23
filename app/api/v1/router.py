"""Aggregate router for API v1.

Mounts every public and admin router under one ``api_router``, which ``main``
mounts at ``/api/v1`` so API versioning lives in exactly one place.
"""

from fastapi import APIRouter

from app.api.v1 import contact, media, projects
from app.api.v1.admin import contacts as admin_contacts
from app.api.v1.admin import media as admin_media
from app.api.v1.admin import projects as admin_projects

api_router = APIRouter()

# Public
api_router.include_router(projects.router)
api_router.include_router(media.router)
api_router.include_router(contact.router)

# Admin (each router requires a valid X-Admin-Token)
api_router.include_router(admin_projects.router)
api_router.include_router(admin_media.router)
api_router.include_router(admin_contacts.router)
