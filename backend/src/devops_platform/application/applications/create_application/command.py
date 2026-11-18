from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from devops_platform.application.software_delivery.shared.models import ApplicationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True)
class ApplicationRegistration:
    environment_id: UUID
    name: str
    template_id: str
    template_version: str


@dataclass(frozen=True, slots=True)
class CreateApplication(Command[tuple[ApplicationDetails, bool]]):
    access: AccessContext
    request: ApplicationRegistration
    idempotency_key: str
    now: datetime
