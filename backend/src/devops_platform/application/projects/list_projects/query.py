from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.projects.result import ProjectRegistrationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadProjects(BaseModel, Query[tuple[ProjectRegistrationDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    user_id: UUID
    accesses: tuple[AccessContext, ...]
