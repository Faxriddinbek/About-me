"""Shared FastAPI dependencies.

Collecting cross-cutting dependencies here (database sessions, authorization)
keeps route modules focused on their own logic and makes the wiring trivial to
override in tests.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_session  # re-exported for routers

__all__ = ["get_session", "get_settings", "require_admin"]


async def require_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Authorize a write request via a bearer token.

    The supplied ``Authorization`` header is compared against ``ADMIN_TOKEN``
    from settings. Defined at the foundation layer so the write endpoints added
    in later steps can simply depend on it. Denies by default when no admin
    token is configured, so a misconfiguration fails closed rather than open.
    """
    expected = settings.ADMIN_TOKEN
    if not expected:
        raise UnauthorizedError("Admin access is not configured.")
    if authorization != f"Bearer {expected}":
        raise UnauthorizedError()
