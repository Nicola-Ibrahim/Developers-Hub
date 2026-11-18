from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadResources(Query[tuple[ResourceDetails, ...]]):
    access: AccessContext
    project_id: UUID
    after: UUID | None
    limit: int
