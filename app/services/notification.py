"""Telegram notification delivery.

Delivery is strictly best-effort: if the bot is not configured the service
no-ops, and any transport or HTTP error is logged and swallowed. Callers can
therefore fire notifications without guarding against failures.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"
_DEFAULT_TIMEOUT_SECONDS = 5.0


class NotificationService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        # An injectable client lets tests supply a mock transport; when absent a
        # short-lived client is created per send.
        self._settings = settings
        self._client = client
        self._timeout = timeout

    async def notify_new_contact(self, *, name: str, email: str, message: str) -> None:
        """Notify the site owner of a new contact message. Never raises."""
        token = self._settings.TELEGRAM_BOT_TOKEN
        chat_id = self._settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            logger.info("Telegram is not configured; skipping contact notification.")
            return

        text = self._format(name, email, message)
        try:
            await self._send(token, chat_id, text)
        except Exception:
            # A failed notification must never propagate to the request path.
            logger.exception("Failed to deliver Telegram contact notification.")

    @staticmethod
    def _format(name: str, email: str, message: str) -> str:
        return f"New contact message\nFrom: {name} <{email}>\n\n{message}"

    async def _send(self, token: str, chat_id: str, text: str) -> None:
        url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        if self._client is not None:
            response = await self._client.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
