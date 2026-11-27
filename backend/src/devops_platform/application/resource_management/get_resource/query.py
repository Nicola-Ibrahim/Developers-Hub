from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadResource(BaseModel, Query[ResourceDetails]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    resource_id: UUID
