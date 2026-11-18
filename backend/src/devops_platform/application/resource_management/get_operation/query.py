from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.resource_management.read_models import OperationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadOperation(Query[OperationDetails]):
    access: AccessContext
    operation_id: UUID
