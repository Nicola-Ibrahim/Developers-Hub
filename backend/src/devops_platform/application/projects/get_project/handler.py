from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.projects.get_project.query import ReadProject
from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.application.shared.errors import resource_not_found


class ReadProjectHandler:
    def __init__(self, repository: ProjectRegistrationRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadProject) -> ProjectRegistrationDetails:
        project = await self.repository.find_project(query.project_id)
        if project is None:
            raise resource_not_found()
        return project
