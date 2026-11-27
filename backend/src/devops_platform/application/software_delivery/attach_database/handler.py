"""Request a database attachment for a registered application."""

from devops_platform.application.interfaces.software_delivery import (
    ApplicationResourceAttachmentRepository,
    RequestFingerprint,
)
from devops_platform.application.software_delivery.attach_database.command import (
    AttachDatabase,
)
from devops_platform.application.software_delivery.shared.models import DeliveryStepDetails


class AttachApplicationResourceHandler:
    def __init__(
        self,
        repository: ApplicationResourceAttachmentRepository,
        fingerprint: RequestFingerprint,
    ) -> None:
        self.repository, self.fingerprint = repository, fingerprint

    async def execute(self, message: AttachDatabase) -> DeliveryStepDetails:
        access, application_id, command = message.access, message.application_id, message.request
        return await self.repository.enqueue_resource_attachment(
            access,
            application_id,
            command,
            message.idempotency_key,
            self.fingerprint.for_value(command),
            message.now,
        )
