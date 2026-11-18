from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from devops_platform.application.interfaces.resources import ResourceSnapshot
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class RenewDatabase(Command[ResourceSnapshot]):
    access: AccessContext
    resource_id: UUID
    expected_revision: int
    expires_at: datetime
