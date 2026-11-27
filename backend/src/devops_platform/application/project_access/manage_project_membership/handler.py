from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)


class ManageProjectMembershipHandler:
    def __init__(self, repository: ProjectAccessRepository) -> None:
        self.repository = repository

    async def execute(self, command: ManageProjectMembership) -> None:
        await self.repository.set_membership(
            actor_id=command.access.user_id,
            user_id=command.user_id,
            project_id=command.project_id,
            role=command.role,
            now=command.now,
        )
