"""Public project endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import LangParam, PaginationParams, ProjectServiceDep
from app.schemas.common import Page
from app.schemas.project import ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=Page[ProjectOut],
    status_code=200,
    summary="List visible projects",
    description=(
        "Return a paginated list of visible projects ordered by display order, "
        "with title/description resolved to the requested language."
    ),
)
async def list_projects(
    service: ProjectServiceDep, lang: LangParam, pagination: PaginationParams
) -> Page[ProjectOut]:
    return await service.list_visible(
        lang=lang, limit=pagination.limit, offset=pagination.offset
    )


@router.get(
    "/{project_id}",
    response_model=ProjectOut,
    status_code=200,
    summary="Get a project",
    description=(
        "Return a single project by id, with text resolved to the requested "
        "language. Responds 404 if the project does not exist."
    ),
)
async def get_project(
    project_id: int, service: ProjectServiceDep, lang: LangParam
) -> ProjectOut:
    return await service.get(project_id, lang=lang)
