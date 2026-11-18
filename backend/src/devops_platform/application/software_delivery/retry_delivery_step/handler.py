"""Retry a failed application delivery step."""

from devops_platform.application.interfaces.software_delivery import (
    DeliveryRetryRepository,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.application.software_delivery.shared.models import DeliveryStepDetails


class RetryDeliveryStepHandler:
    def __init__(self, repository: DeliveryRetryRepository) -> None:
        self.repository = repository

    async def execute(self, command: RetryDeliveryStep) -> DeliveryStepDetails:
        return await self.repository.retry_step(
            command.access, command.application_id, command.step_id, command.now
        )
