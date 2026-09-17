"""Media business logic (mirrors ``ProjectService`` with type/placement filters).

Beyond CRUD, this service owns the rule that a media item and the file behind it
are deleted together — but never in that order. See ``_forget_files``.
"""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.models import MediaPlacement, MediaType
from app.repositories.media import MediaRepository
from app.schemas.common import Lang, Page
from app.schemas.media import MediaAdminOut, MediaCreate, MediaOut, MediaUpdate
from app.services.background import BackgroundRunner
from app.services.storage import FileStorage

# The columns that can hold a URL to a file we stored.
_FILE_FIELDS = ("url", "thumbnail_url")


class MediaService:
    def __init__(self, media: MediaRepository, storage: FileStorage) -> None:
        self._media = media
        self._storage = storage

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
        self,
        media_id: int,
        payload: MediaUpdate,
        *,
        lang: Lang = "uz",
        background: BackgroundRunner | None = None,
    ) -> MediaOut:
        row = await self._media.get(media_id)
        if row is None:
            raise NotFoundError(f"Media item {media_id} was not found.")

        data = payload.model_dump(exclude_unset=True)
        # Captured before the update: once the row is written, the file it used
        # to point at is unreachable and would stay on disk forever.
        replaced = [
            getattr(row, field)
            for field in _FILE_FIELDS
            if field in data and data[field] != getattr(row, field)
        ]

        row = await self._media.update(row, data)
        self._forget_files(replaced, background)
        return MediaOut.from_model(row, lang)

    async def delete(
        self, media_id: int, *, background: BackgroundRunner | None = None
    ) -> None:
        row = await self._media.get(media_id)
        if row is None:
            raise NotFoundError(f"Media item {media_id} was not found.")

        orphaned = [getattr(row, field) for field in _FILE_FIELDS]
        await self._media.delete(row)
        self._forget_files(orphaned, background)

    def _forget_files(
        self, urls: list[str | None], background: BackgroundRunner | None
    ) -> None:
        """Delete the files behind ``urls`` once the transaction has committed.

        Order is the whole point. The scheduler runs after the response is sent,
        which is after the session dependency commits — so a transaction that
        fails takes the scheduled deletions down with it and the files survive.
        Deleting first would invert the failure: a row left pointing at a file
        that no longer exists, which nothing can repair.

        Files the storage does not own (YouTube links, external images) are
        skipped by ``FileStorage.delete`` itself.

        Without a scheduler — a script or a test calling the service directly —
        the deletion happens inline. Every HTTP caller passes one.
        """
        for url in urls:
            if not self._storage.owns(url):
                continue
            if background is not None:
                background.add_task(self._storage.delete, url)
            else:
                self._storage.delete(url)
