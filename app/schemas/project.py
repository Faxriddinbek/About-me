"""Pydantic schemas for the Project domain.

``ProjectOut`` deliberately collapses the bilingual columns into a single
``title`` / ``description`` resolved for the caller's language, so the frontend
never has to know the ``_uz`` / ``_en`` storage exists.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Project
from app.schemas.common import Lang, resolve_translation


class ProjectCreate(BaseModel):
    """Payload for creating a project (both languages required)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title_uz: str = Field(min_length=1, max_length=255)
    title_en: str = Field(min_length=1, max_length=255)
    description_uz: str = Field(min_length=1)
    description_en: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=500)
    display_order: int = 0
    is_visible: bool = True


class ProjectUpdate(BaseModel):
    """Partial update — every field optional; only provided fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title_uz: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, min_length=1, max_length=255)
    description_uz: str | None = Field(default=None, min_length=1)
    description_en: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    image_url: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=500)
    display_order: int | None = None
    is_visible: bool | None = None


class ProjectOut(BaseModel):
    """Single-language, frontend-facing view of a project."""

    id: int
    title: str
    description: str
    tags: list[str]
    image_url: str | None
    link: str | None
    display_order: int
    is_visible: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, project: Project, lang: Lang) -> ProjectOut:
        """Build the view, resolving title/description to ``lang`` (Uzbek fallback)."""
        title = resolve_translation(project.title_uz, project.title_en, lang)
        description = resolve_translation(
            project.description_uz, project.description_en, lang
        )
        return cls(
            id=project.id,
            # ``title_uz`` / ``description_uz`` are NOT NULL, so the fallback is safe.
            title=title or project.title_uz,
            description=description or project.description_uz,
            tags=list(project.tags),
            image_url=project.image_url,
            link=project.link,
            display_order=project.display_order,
            is_visible=project.is_visible,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
