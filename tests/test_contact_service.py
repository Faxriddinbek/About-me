"""Unit tests for ContactService: happy path, rate limiting, and resilience to
Telegram delivery failures.

The repository is mocked (these are unit tests, not integration tests); only the
service's own logic — rate-limit gate, persistence call, and non-blocking,
failure-tolerant notification — is under test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import RateLimitError
from app.models import ContactMessage
from app.schemas.contact import ContactCreate
from app.services.contact import ContactService
from app.services.notification import NotificationService


class RecordingBackground:
    """Stand-in for FastAPI's BackgroundTasks that records scheduled work
    instead of running it, so the test controls when (and whether) it runs."""

    def __init__(self) -> None:
        self.tasks: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None:
        self.tasks.append((func, args, kwargs))


def _payload() -> ContactCreate:
    return ContactCreate(
        name="Ali Valiyev",
        email="ali@example.com",
        message="Assalomu alaykum, loyihangiz bo'yicha bog'lanmoqchiman.",
    )


def _stored_message() -> ContactMessage:
    """A transient model mimicking what the repository returns after persistence."""
    message = ContactMessage(
        id=1,
        name="Ali Valiyev",
        email="ali@example.com",
        message="Assalomu alaykum, loyihangiz bo'yicha bog'lanmoqchiman.",
    )
    message.is_read = False
    message.created_at = datetime.now(UTC)
    return message


async def test_submit_happy_path() -> None:
    repo = AsyncMock()
    repo.count_since.return_value = 0
    repo.create.return_value = _stored_message()
    notifier = AsyncMock(spec=NotificationService)
    service = ContactService(repo, notifier)
    background = RecordingBackground()

    result = await service.submit(
        _payload(), ip_address="1.2.3.4", user_agent="pytest", background=background
    )

    assert result.id == 1
    assert result.is_read is False
    repo.create.assert_awaited_once()
    # The notification is scheduled, not awaited inline (keeps the response fast).
    assert len(background.tasks) == 1
    notifier.notify_new_contact.assert_not_awaited()


async def test_submit_rate_limited() -> None:
    repo = AsyncMock()
    repo.count_since.return_value = 3  # already at the 3-per-hour limit
    notifier = AsyncMock(spec=NotificationService)
    service = ContactService(repo, notifier)

    with pytest.raises(RateLimitError):
        await service.submit(
            _payload(),
            ip_address="1.2.3.4",
            user_agent="pytest",
            background=RecordingBackground(),
        )

    repo.create.assert_not_awaited()  # nothing persisted when rate limited


async def test_submit_survives_telegram_failure() -> None:
    repo = AsyncMock()
    repo.count_since.return_value = 0
    repo.create.return_value = _stored_message()

    # A real notifier whose HTTP transport always fails, with Telegram
    # configured so a send is actually attempted (and must be swallowed).
    settings = Settings(
        ENVIRONMENT="dev",
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_CHAT_ID="123456",
    )

    def _always_fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated telegram outage")

    client = httpx.AsyncClient(transport=httpx.MockTransport(_always_fail))
    notifier = NotificationService(settings, client=client)
    service = ContactService(repo, notifier)
    background = RecordingBackground()

    try:
        result = await service.submit(
            _payload(),
            ip_address="1.2.3.4",
            user_agent="pytest",
            background=background,
        )

        # Submission succeeds and persists despite the notifier being doomed.
        assert result.id == 1
        repo.create.assert_awaited_once()

        # Running the scheduled notification must NOT raise, even though the
        # underlying HTTP call fails — the error is caught and logged.
        func, args, kwargs = background.tasks[0]
        await func(*args, **kwargs)
    finally:
        await client.aclose()
