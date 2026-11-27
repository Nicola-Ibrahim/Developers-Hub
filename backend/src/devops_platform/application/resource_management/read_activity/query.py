from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.interfaces.resources import ResourceActivity
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadResourceActivity(BaseModel, Query[tuple[ResourceActivity, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    project_id: UUID
