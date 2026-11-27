from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.resource_management.read_models import OperationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadOperation(BaseModel, Query[OperationDetails]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    operation_id: UUID
