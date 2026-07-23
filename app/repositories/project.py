"""Data access for :class:`app.models.project.Project`.

Pure persistence: every method takes an ``AsyncSession`` (via the constructor)
and returns ORM models, never schemas. Writes ``flush`` (not ``commit``) so the
request-scoped session in ``get_session`` owns the transaction boundary.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self, *, limit: int, offset: int) -> list[Project]:
        # `WHERE is_visible ORDER BY display_order` — served by the composite
        # index ix_projects_visible_order. `id` is a stable tiebreaker.
        stmt = (
            select(Project)
            .where(Project.is_visible.is_(True))
            .order_by(Project.display_order, Project.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_visible(self) -> int:
        stmt = (
            select(func.count()).select_from(Project).where(Project.is_visible.is_(True))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def get(self, project_id: int) -> Project | None:
        return await self._session.get(Project, project_id)

    async def create(self, data: dict[str, Any]) -> Project:
        project = Project(**data)
        self._session.add(project)
        await self._session.flush()
        await self._session.refresh(project)  # load server defaults (timestamps)
        return project

    async def update(self, project: Project, data: dict[str, Any]) -> Project:
        for field, value in data.items():
            setattr(project, field, value)
        await self._session.flush()
        await self._session.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        await self._session.delete(project)
        await self._session.flush()
