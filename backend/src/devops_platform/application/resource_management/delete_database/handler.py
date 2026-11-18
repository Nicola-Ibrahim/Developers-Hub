from uuid import UUID

from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.delete_database.command import (
    DeleteDatabase,
)


class DeleteTemporaryDatabaseHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, command: DeleteDatabase) -> UUID:
        access = command.access
        return await self.repository.delete(access=access, resource_id=command.resource_id)
