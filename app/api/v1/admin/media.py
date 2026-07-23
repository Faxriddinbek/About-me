"""Admin media management endpoints (create / update / delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import MediaServiceDep, require_admin
from app.schemas.media import MediaCreate, MediaOut, MediaUpdate

router = APIRouter(
    prefix="/admin/media",
    tags=["admin:media"],
    dependencies=[Depends(require_admin)],
)


@router.post(
    "",
    response_model=MediaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a media item",
    description="Create a new gallery item. Requires a valid X-Admin-Token.",
)
async def create_media(payload: MediaCreate, service: MediaServiceDep) -> MediaOut:
    return await service.create(payload)


@router.patch(
    "/{media_id}",
    response_model=MediaOut,
    status_code=status.HTTP_200_OK,
    summary="Update a media item",
    description=(
        "Partially update a media item. Requires a valid X-Admin-Token. "
        "Responds 404 if the item does not exist."
    ),
)
async def update_media(
    media_id: int, payload: MediaUpdate, service: MediaServiceDep
) -> MediaOut:
    return await service.update(media_id, payload)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 204 carries no body; suppress response-model inference
    summary="Delete a media item",
    description=(
        "Delete a media item. Requires a valid X-Admin-Token. "
        "Responds 404 if the item does not exist."
    ),
)
async def delete_media(media_id: int, service: MediaServiceDep) -> None:
    await service.delete(media_id)
