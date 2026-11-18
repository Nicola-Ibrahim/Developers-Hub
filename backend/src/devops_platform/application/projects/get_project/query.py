from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadProject(Query[ProjectRegistrationDetails]):
    access: AccessContext
    project_id: UUID
