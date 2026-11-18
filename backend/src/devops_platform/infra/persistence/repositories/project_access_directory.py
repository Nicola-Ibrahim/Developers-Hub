"""SQLAlchemy adapter for operator-managed project and team references."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.domain.interfaces.project_access_directory import ProjectAccessReferences
from devops_platform.infra.persistence.models.project_access import ProjectRow, TeamRow
from shared.infra.persistence.unit_of_work import DatabaseUnavailable


class SQLAlchemyProjectAccessDirectory:
    """Register project and team references without creating memberships or committing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_references(
        self, project_name: str, team_name: str
    ) -> ProjectAccessReferences:
        await self._session.execute(
            insert(TeamRow)
            .values(name=team_name)
            .on_conflict_do_nothing(index_elements=[TeamRow.name])
        )
        team = await self._session.scalar(
            select(TeamRow).where(TeamRow.name == team_name).with_for_update()
        )
        if team is None:
            raise DatabaseUnavailable()

        await self._session.execute(
            insert(ProjectRow)
            .values(name=project_name)
            .on_conflict_do_nothing(index_elements=[ProjectRow.name])
        )
        project = await self._session.scalar(
            select(ProjectRow).where(ProjectRow.name == project_name).with_for_update()
        )
        if project is None:
            raise DatabaseUnavailable()

        return ProjectAccessReferences(project_id=project.id, team_id=team.id)
