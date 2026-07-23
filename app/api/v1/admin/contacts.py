"""Admin contact-message endpoints (list / mark read)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ContactServiceDep, PaginationParams, require_admin
from app.schemas.common import Page
from app.schemas.contact import ContactOut

router = APIRouter(
    prefix="/admin/contacts",
    tags=["admin:contacts"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=Page[ContactOut],
    status_code=status.HTTP_200_OK,
    summary="List contact messages",
    description=(
        "List contact messages newest-first, optionally only unread ones. "
        "Requires a valid X-Admin-Token."
    ),
)
async def list_contacts(
    service: ContactServiceDep,
    pagination: PaginationParams,
    unread_only: Annotated[bool, Query(description="Only return unread messages.")] = False,
) -> Page[ContactOut]:
    return await service.list(
        limit=pagination.limit, offset=pagination.offset, unread_only=unread_only
    )


@router.patch(
    "/{message_id}/read",
    response_model=ContactOut,
    status_code=status.HTTP_200_OK,
    summary="Mark a message read",
    description=(
        "Mark a contact message as read. Requires a valid X-Admin-Token. "
        "Responds 404 if the message does not exist."
    ),
)
async def mark_contact_read(message_id: int, service: ContactServiceDep) -> ContactOut:
    return await service.mark_read(message_id)
