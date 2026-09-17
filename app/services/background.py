"""Scheduling work that must happen *after* the response, not during it.

Two services need this for different reasons: a notification must not delay the
reply, and a file deletion must not happen until the database transaction it
follows has actually committed. Declaring the scheduler structurally (rather
than importing ``fastapi.BackgroundTasks``) keeps the service layer free of the
web framework, and lets tests pass a plain stub.
"""

from __future__ import annotations

from typing import Any, Protocol


class BackgroundRunner(Protocol):
    """Anything that can run a callable once the request is done."""

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None: ...
