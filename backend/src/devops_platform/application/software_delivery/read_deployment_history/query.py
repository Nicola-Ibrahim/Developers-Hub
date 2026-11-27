from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.software_delivery.shared.models import DeploymentDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadDeploymentHistory(BaseModel, Query[tuple[DeploymentDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
    application_id: UUID
