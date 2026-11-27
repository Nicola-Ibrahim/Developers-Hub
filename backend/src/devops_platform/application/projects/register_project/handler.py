"""Register an approved project and its environments."""

from uuid import UUID

from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.projects.register_project.command import RegisterProjectCommand
from devops_platform.application.projects.result import ProjectRegistrationDetails


class RegisterProjectHandler:
    def __init__(self, repository: ProjectRegistrationRepository) -> None:
        self.repository = repository

    async def execute(
        self, command: RegisterProjectCommand, project_id: UUID, team_id: UUID
    ) -> ProjectRegistrationDetails:
        return await self.repository.register_project(command, project_id, team_id)
