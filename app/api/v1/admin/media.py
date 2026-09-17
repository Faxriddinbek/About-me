"""Admin media management endpoints (list / create / update / delete)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import FileStorageDep, MediaServiceDep, PaginationParams, require_admin
from app.models import MediaPlacement, MediaType
from app.schemas.common import Page
from app.schemas.media import MediaAdminOut, MediaCreate, MediaOut, MediaUpdate


class UploadOut(BaseModel):
    """Where an uploaded file now lives, ready to be stored on a media item."""

    url: str

router = APIRouter(
    prefix="/admin/media",
    tags=["admin:media"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=Page[MediaAdminOut],
    status_code=status.HTTP_200_OK,
    summary="List every media item",
    description=(
        "List all media items, hidden ones included, with both language columns "
        "unresolved. Requires a valid X-Admin-Token."
    ),
)
async def list_media(
    service: MediaServiceDep,
    pagination: PaginationParams,
    media_type: Annotated[
        MediaType | None, Query(alias="type", description="Filter by media type.")
    ] = None,
    placement: Annotated[
        MediaPlacement | None, Query(description="Filter by placement.")
    ] = None,
) -> Page[MediaAdminOut]:
    return await service.list_all(
        media_type=media_type,
        placement=placement,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/upload",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image",
    description=(
        "Store an image file and return the URL to serve it from. Create the "
        "media item separately with that URL — uploading and recording are kept "
        "apart so a failed save never orphans a row. Requires a valid "
        "X-Admin-Token."
    ),
)
async def upload_file(
    storage: FileStorageDep, file: Annotated[UploadFile, File()]
) -> UploadOut:
    return UploadOut(url=await storage.save(file))


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
