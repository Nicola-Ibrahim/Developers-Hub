from dataclasses import dataclass

from devops_platform.application.software_delivery.shared.models import ApplicationDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadApplications(Query[tuple[ApplicationDetails, ...]]):
    access: AccessContext
