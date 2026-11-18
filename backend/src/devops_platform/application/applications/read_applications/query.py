from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.software_delivery.shared.models import (
    ApplicationDetails,
    DeliveryStepDetails,
    DeploymentDetails,
)
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadApplications(Query[tuple[ApplicationDetails, ...]]):
    access: AccessContext


@dataclass(frozen=True, slots=True)
class ReadApplication(Query[tuple[ApplicationDetails, tuple[DeliveryStepDetails, ...]]]):
    access: AccessContext
    application_id: UUID


@dataclass(frozen=True, slots=True)
class ReadDeploymentHistory(Query[tuple[DeploymentDetails, ...]]):
    access: AccessContext
    application_id: UUID
