"""Persistence required to register an application-generation request."""

from datetime import datetime
from typing import Protocol

from devops_platform.application.applications.create_application.command import (
    ApplicationRegistration,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.software_delivery.shared.models import WorkloadDetails


class ApplicationCreationRepository(Protocol):
    async def create_application(
        self,
        access: AccessContext,
        command: ApplicationRegistration,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> tuple[WorkloadDetails, bool]: ...
