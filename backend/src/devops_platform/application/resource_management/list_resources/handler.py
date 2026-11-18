from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.list_resources.query import ReadResources
from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.application.shared.errors import PlatformRequestError


class ReadResourcesHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadResources) -> tuple[ResourceDetails, ...]:
        if not 1 <= query.limit <= 100:
            raise PlatformRequestError("invalid_page", "Page limit must be between 1 and 100", 422)
        return await self.repository.list_resources(query.project_id, query.after, query.limit)
