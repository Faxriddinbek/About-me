"""Contact-form business logic: rate-limited submission with fire-and-forget
notification.

The notification is scheduled off the request path and the notifier swallows its
own errors, so notifying can neither block nor break a submission.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.core.exceptions import NotFoundError, RateLimitError
from app.repositories.contact import ContactRepository
from app.schemas.common import Page
from app.schemas.contact import ContactCreate, ContactOut
from app.services.notification import NotificationService

# Business rule: throttle submissions per source IP. Named constants (not inline
# literals) so the policy is explicit and easy to tune.
_MAX_MESSAGES_PER_WINDOW = 3
_RATE_LIMIT_WINDOW = timedelta(hours=1)


class BackgroundRunner(Protocol):
    """Structural type for a background-task scheduler such as FastAPI's
    ``BackgroundTasks``. Declared here so this service never imports FastAPI."""

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None: ...


class ContactService:
    def __init__(
        self, contacts: ContactRepository, notifier: NotificationService
    ) -> None:
        self._contacts = contacts
        self._notifier = notifier
        # Hold strong references to fire-and-forget tasks so the event loop does
        # not garbage-collect them mid-flight (used only on the no-scheduler path).
        self._pending: set[asyncio.Task[Any]] = set()

    async def submit(
        self,
        payload: ContactCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
        background: BackgroundRunner | None = None,
    ) -> ContactOut:
        """Rate-limit, persist, and schedule a notification for a new message."""
        window_start = datetime.now(UTC) - _RATE_LIMIT_WINDOW
        recent = await self._contacts.count_since(ip_address, window_start)
        if recent >= _MAX_MESSAGES_PER_WINDOW:
            raise RateLimitError(
                "You have sent too many messages recently. Please try again later."
            )

        message = await self._contacts.create(
            {
                "name": payload.name,
                "email": payload.email,
                "message": payload.message,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )
        self._schedule_notification(payload, background)
        return ContactOut.model_validate(message)

    async def list(
        self, *, limit: int, offset: int, unread_only: bool = False
    ) -> Page[ContactOut]:
        rows = await self._contacts.list(
            limit=limit, offset=offset, unread_only=unread_only
        )
        total = await self._contacts.count(unread_only=unread_only)
        return Page[ContactOut](
            items=[ContactOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def mark_read(self, message_id: int) -> ContactOut:
        row = await self._contacts.mark_read(message_id)
        if row is None:
            raise NotFoundError(f"Contact message {message_id} was not found.")
        return ContactOut.model_validate(row)

    def _schedule_notification(
        self, payload: ContactCreate, background: BackgroundRunner | None
    ) -> None:
        """Schedule the Telegram notification without awaiting it.

        Prefers the caller's background-task runner (e.g. FastAPI's, which runs
        after the response is sent); falls back to a tracked ``asyncio`` task.
        """
        if background is not None:
            background.add_task(
                self._notifier.notify_new_contact,
                name=payload.name,
                email=payload.email,
                message=payload.message,
            )
            return

        task = asyncio.create_task(
            self._notifier.notify_new_contact(
                name=payload.name, email=payload.email, message=payload.message
            )
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
