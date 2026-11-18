from devops_platform.application.applications.get_application.query import ReadApplication
from devops_platform.application.interfaces.applications import (
    ApplicationReadRepository,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import (
    ApplicationDetails,
    DeliveryStepDetails,
)


class ReadApplicationHandler:
    def __init__(self, repository: ApplicationReadRepository) -> None:
        self.repository = repository

    async def execute(
        self, query: ReadApplication
    ) -> tuple[ApplicationDetails, tuple[DeliveryStepDetails, ...]]:
        application = await self.repository.find_application(
            query.access.project_id, query.application_id
        )
        if application is None:
            raise PlatformRequestError("workload_not_found", "Application was not found", 404)
        return application, await self.repository.list_steps(application.id)
