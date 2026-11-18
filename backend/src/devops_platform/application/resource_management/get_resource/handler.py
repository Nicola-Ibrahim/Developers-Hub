from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.get_resource.query import ReadResource
from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.application.shared.errors import resource_not_found


class ReadResourceHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadResource) -> ResourceDetails:
        resource = await self.repository.find_resource(query.access.project_id, query.resource_id)
        if resource is None:
            raise resource_not_found()
        return resource
