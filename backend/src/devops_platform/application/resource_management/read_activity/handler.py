from devops_platform.application.interfaces.resources import (
    ResourceActivity,
    ResourceRepository,
)
from devops_platform.application.resource_management.read_activity.query import (
    ReadResourceActivity,
)


class ListResourceActivityQueryHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadResourceActivity) -> tuple[ResourceActivity, ...]:
        return await self.repository.activity(query.project_id, 100)
