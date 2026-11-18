from devops_platform.application.applications.list_applications.query import ReadApplications
from devops_platform.application.interfaces.applications import (
    ApplicationReadRepository,
)
from devops_platform.application.software_delivery.shared.models import ApplicationDetails


class ReadApplicationsHandler:
    def __init__(self, repository: ApplicationReadRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadApplications) -> tuple[ApplicationDetails, ...]:
        return await self.repository.list_applications(query.access.project_id)
