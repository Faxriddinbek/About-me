"""Pydantic schemas for the Media domain.

Like ``ProjectOut``, ``MediaOut`` resolves the bilingual ``title_*`` columns to a
single ``title`` for the caller's language (nullable — media titles are optional).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import MediaItem, MediaType
from app.schemas.common import Lang, resolve_translation


class MediaCreate(BaseModel):
    """Payload for creating a gallery item."""

    model_config = ConfigDict(str_strip_whitespace=True)

    media_type: MediaType
    url: str = Field(min_length=1, max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    title_uz: str | None = Field(default=None, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    display_order: int = 0
    is_visible: bool = True


class MediaUpdate(BaseModel):
    """Partial update — every field optional; only provided fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    media_type: MediaType | None = None
    url: str | None = Field(default=None, min_length=1, max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    title_uz: str | None = Field(default=None, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    display_order: int | None = None
    is_visible: bool | None = None


class MediaOut(BaseModel):
    """Single-language, frontend-facing view of a gallery item."""

    id: int
    media_type: MediaType
    url: str
    thumbnail_url: str | None
    title: str | None
    display_order: int
    is_visible: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, media: MediaItem, lang: Lang) -> MediaOut:
        """Build the view, resolving the optional title to ``lang`` (Uzbek fallback)."""
        return cls(
            id=media.id,
            media_type=media.media_type,
            url=media.url,
            thumbnail_url=media.thumbnail_url,
            title=resolve_translation(media.title_uz, media.title_en, lang),
            display_order=media.display_order,
            is_visible=media.is_visible,
            created_at=media.created_at,
            updated_at=media.updated_at,
        )
