from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.projects.list_projects.query import ReadProjects
from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.application.shared.errors import resource_not_found


class ReadProjectsHandler:
    def __init__(self, repository: ProjectRegistrationRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadProjects) -> tuple[ProjectRegistrationDetails, ...]:
        results = []
        for access in query.accesses:
            project = await self.repository.find_project(access.project_id)
            if project is None:
                raise resource_not_found()
            results.append(project)
        return tuple(results)
