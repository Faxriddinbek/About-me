"""Data access for :class:`app.models.contact.ContactMessage`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContactMessage


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict[str, Any]) -> ContactMessage:
        message = ContactMessage(**data)
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def list(
        self, *, limit: int, offset: int, unread_only: bool = False
    ) -> list[ContactMessage]:
        stmt = select(ContactMessage)
        if unread_only:
            stmt = stmt.where(ContactMessage.is_read.is_(False))
        stmt = (
            stmt.order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, unread_only: bool = False) -> int:
        stmt = select(func.count()).select_from(ContactMessage)
        if unread_only:
            stmt = stmt.where(ContactMessage.is_read.is_(False))
        return int((await self._session.execute(stmt)).scalar_one())

    async def mark_read(self, message_id: int) -> ContactMessage | None:
        message = await self._session.get(ContactMessage, message_id)
        if message is None:
            return None
        message.is_read = True
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def count_since(self, ip_address: str | None, since: datetime) -> int:
        """Count messages from one IP within a time window (for rate limiting)."""
        stmt = (
            select(func.count())
            .select_from(ContactMessage)
            .where(ContactMessage.created_at >= since)
        )
        if ip_address is None:
            stmt = stmt.where(ContactMessage.ip_address.is_(None))
        else:
            stmt = stmt.where(ContactMessage.ip_address == ip_address)
        return int((await self._session.execute(stmt)).scalar_one())
