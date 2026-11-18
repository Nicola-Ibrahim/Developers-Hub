from devops_platform.application.interfaces.resources import (
    ResourceRepository,
    ResourceSnapshot,
)
from devops_platform.application.resource_management.renew_lease.command import (
    RenewDatabase,
)


class RenewDatabaseLeaseHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, command: RenewDatabase) -> ResourceSnapshot:
        access = command.access
        return await self.repository.renew(
            access=access,
            resource_id=command.resource_id,
            revision=command.expected_revision,
            expiry=command.expires_at,
        )
