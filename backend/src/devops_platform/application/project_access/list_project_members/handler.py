from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.application.project_access.list_project_members.query import (
    ListProjectMembers,
    ProjectMemberDetails,
)


class ListProjectMembersHandler:
    def __init__(self, repository: ProjectAccessRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListProjectMembers) -> tuple[ProjectMemberDetails, ...]:
        return await self.repository.list_project_members(
            actor_id=query.access.user_id, project_id=query.project_id
        )
