"""Public media endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import LangParam, MediaServiceDep, PaginationParams
from app.models import MediaPlacement, MediaType
from app.schemas.common import Page
from app.schemas.media import MediaOut

router = APIRouter(prefix="/media", tags=["media"])


@router.get(
    "",
    response_model=Page[MediaOut],
    status_code=200,
    summary="List visible media",
    description=(
        "Return a paginated list of visible media items, optionally filtered by "
        "type (photo|video) and placement (hero|gallery), with titles resolved "
        "to the requested language."
    ),
)
async def list_media(
    service: MediaServiceDep,
    lang: LangParam,
    pagination: PaginationParams,
    media_type: Annotated[
        MediaType | None, Query(alias="type", description="Filter by media type.")
    ] = None,
    placement: Annotated[
        MediaPlacement | None,
        Query(description="Filter by placement: hero (home carousel) or gallery."),
    ] = None,
) -> Page[MediaOut]:
    return await service.list_visible(
        lang=lang,
        media_type=media_type,
        placement=placement,
        limit=pagination.limit,
        offset=pagination.offset,
    )
