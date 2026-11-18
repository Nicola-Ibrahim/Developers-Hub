from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.software_delivery.shared.models import DeploymentDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadDeploymentHistory(Query[tuple[DeploymentDetails, ...]]):
    access: AccessContext
    application_id: UUID
