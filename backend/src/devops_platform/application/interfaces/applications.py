"""Application contracts grouped by capability."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from devops_platform.application.applications.create_application.command import (
    ApplicationRegistration,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.software_delivery.shared.models import (
    DeliveryStepDetails,
    DeploymentDetails,
    WorkloadDetails,
)

"""Persistence required to register an application-generation request."""


class ApplicationCreationRepository(Protocol):
    async def create_application(
        self,
        access: AccessContext,
        command: ApplicationRegistration,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> tuple[WorkloadDetails, bool]: ...


"""Read-only projection access for application delivery."""


class ApplicationReadRepository(Protocol):
    async def list_applications(self, project_id: UUID) -> tuple[WorkloadDetails, ...]: ...
    async def find_application(
        self, project_id: UUID, application_id: UUID
    ) -> WorkloadDetails | None: ...
    async def list_steps(self, application_id: UUID) -> tuple[DeliveryStepDetails, ...]: ...
    async def deployment_history(
        self, project_id: UUID, application_id: UUID
    ) -> tuple[DeploymentDetails, ...]: ...
