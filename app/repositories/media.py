"""Data access for :class:`app.models.media.MediaItem`.

The optional ``media_type`` argument only shapes the query; it carries no
business meaning, so it stays here rather than in a service.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaItem, MediaType


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(
        self, *, media_type: MediaType | None = None, limit: int, offset: int
    ) -> list[MediaItem]:
        # `WHERE is_visible [AND media_type = ?] ORDER BY display_order` —
        # the leading columns match ix_media_items_visible_order.
        stmt = select(MediaItem).where(MediaItem.is_visible.is_(True))
        if media_type is not None:
            stmt = stmt.where(MediaItem.media_type == media_type)
        stmt = (
            stmt.order_by(MediaItem.display_order, MediaItem.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_visible(self, *, media_type: MediaType | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(MediaItem)
            .where(MediaItem.is_visible.is_(True))
        )
        if media_type is not None:
            stmt = stmt.where(MediaItem.media_type == media_type)
        return int((await self._session.execute(stmt)).scalar_one())

    async def get(self, media_id: int) -> MediaItem | None:
        return await self._session.get(MediaItem, media_id)

    async def create(self, data: dict[str, Any]) -> MediaItem:
        item = MediaItem(**data)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def update(self, item: MediaItem, data: dict[str, Any]) -> MediaItem:
        for field, value in data.items():
            setattr(item, field, value)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def delete(self, item: MediaItem) -> None:
        await self._session.delete(item)
        await self._session.flush()
