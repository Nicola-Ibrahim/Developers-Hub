from pydantic import BaseModel, ConfigDict

from devops_platform.application.software_delivery.shared.models import ApplicationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadApplications(BaseModel, Query[tuple[ApplicationDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
