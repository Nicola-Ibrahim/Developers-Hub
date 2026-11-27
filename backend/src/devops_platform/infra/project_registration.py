"""Transactional Platform project registration and first-admin setup."""

from collections.abc import Awaitable, Callable

from devops_platform.application.projects.register_project.command import RegisterProjectCommand
from devops_platform.application.projects.register_project.handler import (
    RegisterProjectHandler,
)
from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.application.shared.errors import ledger_unavailable
from devops_platform.domain.interfaces.project_access_directory import ProjectAccessDirectory
from shared.application.interfaces.unit_of_work import UnitOfWork
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork


class RegisterProjectCommandHandler:
    def __init__(
        self,
        directory: ProjectAccessDirectory,
        register: RegisterProjectHandler,
        unit: UnitOfWork,
    ) -> None:
        self.directory = directory
        self.register = register
        self.unit = unit

    async def execute(self, command: RegisterProjectCommand) -> ProjectRegistrationDetails:
        async def register() -> ProjectRegistrationDetails:
            refs = await self.directory.register_references(command.name, command.owning_team)
            return await self.register.execute(command, refs.project_id, refs.team_id)

        return await self.unit.run(register, lambda result: result)


class ProjectUnitOfWork(UnitOfWork):
    def __init__(self, unit: SqlAlchemyUnitOfWork) -> None:
        self._unit = unit

    async def run[T, R](
        self, action: Callable[[], Awaitable[T]], materialize: Callable[[T], R]
    ) -> R:
        try:
            return await self._unit.run(action, materialize)
        except DatabaseUnavailable as error:
            raise ledger_unavailable() from error
