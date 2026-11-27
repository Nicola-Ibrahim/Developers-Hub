from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.list_resources.query import ReadResources
from devops_platform.application.resource_management.read_models import ResourceDetails


class ReadResourcesHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadResources) -> tuple[ResourceDetails, ...]:
        return await self.repository.list_resources(query.project_id, query.after, query.limit)
