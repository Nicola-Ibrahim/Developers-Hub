from devops_platform.application.interfaces.applications import (
    ApplicationReadRepository,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.read_deployment_history.query import (
    ReadDeploymentHistory,
)
from devops_platform.application.software_delivery.shared.models import DeploymentDetails


class ReadDeploymentHistoryHandler:
    def __init__(self, repository: ApplicationReadRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadDeploymentHistory) -> tuple[DeploymentDetails, ...]:
        if (
            await self.repository.find_application(query.access.project_id, query.application_id)
            is None
        ):
            raise PlatformRequestError("workload_not_found", "Application was not found", 404)
        return await self.repository.deployment_history(
            query.access.project_id, query.application_id
        )
