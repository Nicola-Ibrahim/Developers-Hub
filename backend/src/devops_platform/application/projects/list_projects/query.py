from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadProjects(Query[tuple[ProjectRegistrationDetails, ...]]):
    user_id: UUID
    accesses: tuple[AccessContext, ...]
