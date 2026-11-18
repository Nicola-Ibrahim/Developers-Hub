from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.interfaces.resources import ResourceActivity
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadResourceActivity(Query[tuple[ResourceActivity, ...]]):
    access: AccessContext
    project_id: UUID
