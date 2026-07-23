"""Admin project management endpoints (create / update / delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import ProjectServiceDep, require_admin
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(
    prefix="/admin/projects",
    tags=["admin:projects"],
    dependencies=[Depends(require_admin)],
)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description="Create a new project. Requires a valid X-Admin-Token.",
)
async def create_project(payload: ProjectCreate, service: ProjectServiceDep) -> ProjectOut:
    return await service.create(payload)


@router.patch(
    "/{project_id}",
    response_model=ProjectOut,
    status_code=status.HTTP_200_OK,
    summary="Update a project",
    description=(
        "Partially update a project. Requires a valid X-Admin-Token. "
        "Responds 404 if the project does not exist."
    ),
)
async def update_project(
    project_id: int, payload: ProjectUpdate, service: ProjectServiceDep
) -> ProjectOut:
    return await service.update(project_id, payload)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 204 carries no body; suppress response-model inference
    summary="Delete a project",
    description=(
        "Delete a project. Requires a valid X-Admin-Token. "
        "Responds 404 if the project does not exist."
    ),
)
async def delete_project(project_id: int, service: ProjectServiceDep) -> None:
    await service.delete(project_id)
