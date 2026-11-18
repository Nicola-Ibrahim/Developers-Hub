from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.application.project_access.bootstrap_first_admin.command import (
    BootstrapFirstAdmin,
)
from shared.application.interfaces.unit_of_work import UnitOfWork


class BootstrapFirstAdminHandler:
    def __init__(self, repository: ProjectAccessRepository, unit: UnitOfWork) -> None:
        self.repository, self.unit = repository, unit

    async def execute(self, command: BootstrapFirstAdmin) -> None:
        await self.unit.run(
            lambda: self.repository.bootstrap_first_project_admin(
                user_id=command.user_id, project_id=command.project_id, now=command.now
            ),
            lambda result: result,
        )
