from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from devops_platform.application.software_delivery.shared.models import DeliveryStepDetails
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class RetryDeliveryStep(Command[DeliveryStepDetails]):
    access: AccessContext
    application_id: UUID
    step_id: UUID
    now: datetime
