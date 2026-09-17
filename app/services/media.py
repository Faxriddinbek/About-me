"""Media business logic (mirrors ``ProjectService`` with type/placement filters)."""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.models import MediaPlacement, MediaType
from app.repositories.media import MediaRepository
from app.schemas.common import Lang, Page
from app.schemas.media import MediaAdminOut, MediaCreate, MediaOut, MediaUpdate


class MediaService:
    def __init__(self, media: MediaRepository) -> None:
        self._media = media

    async def list_visible(
        self,
        *,
        lang: Lang,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
        limit: int,
        offset: int,
    ) -> Page[MediaOut]:
        rows = await self._media.list_visible(
            media_type=media_type, placement=placement, limit=limit, offset=offset
        )
        total = await self._media.count_visible(
            media_type=media_type, placement=placement
        )
        return Page[MediaOut](
            items=[MediaOut.from_model(row, lang) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_all(
        self,
        *,
        media_type: MediaType | None = None,
        placement: MediaPlacement | None = None,
        limit: int,
        offset: int,
    ) -> Page[MediaAdminOut]:
        """Admin listing: every item, hidden ones included, both languages raw."""
        rows = await self._media.list_all(
            media_type=media_type, placement=placement, limit=limit, offset=offset
        )
        total = await self._media.count_all(media_type=media_type, placement=placement)
        return Page[MediaAdminOut](
            items=[MediaAdminOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get(self, media_id: int, *, lang: Lang) -> MediaOut:
        row = await self._media.get(media_id)
        if row is None:
            raise NotFoundError(f"Media item {media_id} was not found.")
        return MediaOut.from_model(row, lang)

    async def create(self, payload: MediaCreate, *, lang: Lang = "uz") -> MediaOut:
        row = await self._media.create(payload.model_dump())
        return MediaOut.from_model(row, lang)

    async def update(
        self, media_id: int, payload: MediaUpdate, *, lang: Lang = "uz"
    ) -> MediaOut:
        row = await self._media.get(media_id)
        if row is None:
            raise NotFoundError(f"Media item {media_id} was not found.")
        row = await self._media.update(row, payload.model_dump(exclude_unset=True))
        return MediaOut.from_model(row, lang)

    async def delete(self, media_id: int) -> None:
        row = await self._media.get(media_id)
        if row is None:
            raise NotFoundError(f"Media item {media_id} was not found.")
        await self._media.delete(row)
