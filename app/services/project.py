"""Project business logic.

Orchestrates the repository into API-shaped results (``Page`` / ``*Out``) and
raises domain exceptions — never HTTP errors, never FastAPI imports.
"""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.project import ProjectRepository
from app.schemas.common import Lang, Page
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate


class ProjectService:
    def __init__(self, projects: ProjectRepository) -> None:
        self._projects = projects

    async def list_visible(self, *, lang: Lang, limit: int, offset: int) -> Page[ProjectOut]:
        rows = await self._projects.list_visible(limit=limit, offset=offset)
        total = await self._projects.count_visible()
        return Page[ProjectOut](
            items=[ProjectOut.from_model(row, lang) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get(self, project_id: int, *, lang: Lang) -> ProjectOut:
        row = await self._projects.get(project_id)
        if row is None:
            raise NotFoundError(f"Project {project_id} was not found.")
        return ProjectOut.from_model(row, lang)

    async def create(self, payload: ProjectCreate, *, lang: Lang = "uz") -> ProjectOut:
        row = await self._projects.create(payload.model_dump())
        return ProjectOut.from_model(row, lang)

    async def update(
        self, project_id: int, payload: ProjectUpdate, *, lang: Lang = "uz"
    ) -> ProjectOut:
        row = await self._projects.get(project_id)
        if row is None:
            raise NotFoundError(f"Project {project_id} was not found.")
        row = await self._projects.update(row, payload.model_dump(exclude_unset=True))
        return ProjectOut.from_model(row, lang)

    async def delete(self, project_id: int) -> None:
        row = await self._projects.get(project_id)
        if row is None:
            raise NotFoundError(f"Project {project_id} was not found.")
        await self._projects.delete(row)
