"""Shared FastAPI dependencies: sessions, repositories, services, auth, and
request-parameter parsing.

The session -> repository -> service chain is assembled here with ``Depends`` so
that route handlers only ever receive a fully constructed *service* — they never
touch a session or repository directly.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_session
from app.repositories.contact import ContactRepository
from app.repositories.media import MediaRepository
from app.repositories.project import ProjectRepository
from app.schemas.common import Lang
from app.services.contact import ContactService
from app.services.media import MediaService
from app.services.notification import NotificationService
from app.services.project import ProjectService
from app.services.storage import FileStorage

__all__ = [
    "ContactServiceDep",
    "FileStorageDep",
    "LangParam",
    "MediaServiceDep",
    "PaginationParams",
    "ProjectServiceDep",
    "SettingsDep",
    "get_client_ip",
    "get_session",
    "get_settings",
    "require_admin",
]

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# --- Repository providers ----------------------------------------------------
def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


def get_media_repository(session: SessionDep) -> MediaRepository:
    return MediaRepository(session)


def get_contact_repository(session: SessionDep) -> ContactRepository:
    return ContactRepository(session)


# --- Service providers -------------------------------------------------------
def get_notification_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationService:
    return NotificationService(settings)


def get_project_service(
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ProjectService:
    return ProjectService(repo)


def get_media_service(
    repo: Annotated[MediaRepository, Depends(get_media_repository)],
) -> MediaService:
    return MediaService(repo)


def get_contact_service(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    notifier: Annotated[NotificationService, Depends(get_notification_service)],
) -> ContactService:
    return ContactService(repo, notifier)


def get_file_storage(settings: SettingsDep) -> FileStorage:
    return FileStorage(settings)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
MediaServiceDep = Annotated[MediaService, Depends(get_media_service)]
ContactServiceDep = Annotated[ContactService, Depends(get_contact_service)]
FileStorageDep = Annotated[FileStorage, Depends(get_file_storage)]


# --- Authentication ----------------------------------------------------------
def require_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    """Authorize admin requests via the ``X-Admin-Token`` header.

    Uses ``secrets.compare_digest`` for a constant-time comparison; a plain
    ``==`` would leak how many leading characters matched via timing. Denies by
    default when no token is configured (fail closed).
    """
    expected = settings.ADMIN_TOKEN
    if not expected:
        raise UnauthorizedError("Admin access is not configured.")
    if not secrets.compare_digest(x_admin_token or "", expected):
        raise UnauthorizedError("Invalid admin token.")


# --- Request parameters ------------------------------------------------------
def get_lang(
    lang: Annotated[Lang, Query(description="Response language (uz|en).")] = "uz",
) -> Lang:
    """Validate ``?lang=`` against the allowed set, defaulting to Uzbek."""
    return lang


LangParam = Annotated[Lang, Depends(get_lang)]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def get_pagination(
    limit: Annotated[int, Query(ge=1, le=100, description="Max items (1-100).")] = 20,
    offset: Annotated[int, Query(ge=0, description="Items to skip.")] = 0,
) -> Pagination:
    """Parse pagination, enforcing ``limit <= 100`` (rejected with 422 otherwise)."""
    return Pagination(limit=limit, offset=offset)


PaginationParams = Annotated[Pagination, Depends(get_pagination)]


# --- Client IP (proxy-aware) -------------------------------------------------
def get_client_ip(request: Request) -> str:
    """Resolve the client IP, honouring ``X-Forwarded-For`` only when trusted.

    The header is attacker-controllable, so it is used only when ``TRUST_PROXY``
    is enabled (i.e. the app sits behind a proxy that sets it). The first entry
    is the original client; subsequent entries are intermediary proxies.
    """
    settings = get_settings()
    if settings.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
