"""Data access for :class:`app.models.media.MediaItem`.

The optional ``media_type`` and ``placement`` arguments only shape the query;
they carry no business meaning, so they stay here rather than in a service.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaItem, MediaPlacement, MediaType


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        *,
        media_type: MediaType | None,
        placement: MediaPlacement | None,
    ) -> Select[Any]:
        """Attach the optional type/placement predicates shared by every query."""
        if media_type is not None:
            stmt = stmt.where(MediaItem.media_type == media_type)
        if placement is not None:
            stmt = stmt.where(MediaItem.placement == placement)
        return stmt

    async def list_visible(
        self,
        *,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
        limit: int,
        offset: int,
    ) -> list[MediaItem]:
        # `WHERE [placement = ?] AND is_visible [AND media_type = ?]
        #  ORDER BY display_order` — the leading columns match
        # ix_media_items_placement_visible_order.
        stmt = select(MediaItem).where(MediaItem.is_visible.is_(True))
        stmt = self._apply_filters(stmt, media_type=media_type, placement=placement)
        stmt = (
            stmt.order_by(MediaItem.display_order, MediaItem.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_visible(
        self,
        *,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(MediaItem)
            .where(MediaItem.is_visible.is_(True))
        )
        stmt = self._apply_filters(stmt, media_type=media_type, placement=placement)
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_all(
        self,
        *,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
        limit: int,
        offset: int,
    ) -> list[MediaItem]:
        """List items regardless of visibility — the admin panel's view.

        Hidden rows are exactly what an admin needs to see in order to unhide
        them, so this deliberately omits the ``is_visible`` predicate.
        """
        stmt = select(MediaItem)
        stmt = self._apply_filters(stmt, media_type=media_type, placement=placement)
        stmt = (
            stmt.order_by(MediaItem.placement, MediaItem.display_order, MediaItem.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(MediaItem)
        stmt = self._apply_filters(stmt, media_type=media_type, placement=placement)
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
