"""Shared schema types: language handling and the generic pagination wrapper."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

Lang = Literal["uz", "en"]
"""Supported response languages. Uzbek is the site's primary/default language."""

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A single page of results plus the totals needed to paginate.

    Generic over the item type so every list endpoint returns the same envelope
    (``{items, total, limit, offset}``) regardless of domain.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


def resolve_translation(uz: str | None, en: str | None, lang: Lang) -> str | None:
    """Resolve a bilingual (``_uz`` / ``_en``) pair to the requested language.

    Falls back to Uzbek when English is requested but blank/missing, because
    Uzbek is the primary language and is always populated for required fields.
    """
    if lang == "en" and en and en.strip():
        return en
    return uz
