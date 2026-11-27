from devops_platform.application.interfaces.software_delivery import (
    LocalPreviewRepository,
    RequestFingerprint,
)
from devops_platform.application.software_delivery.create_local_preview.command import (
    CreateLocalPreview,
)
from devops_platform.application.software_delivery.shared.models import WorkloadDetails


class CreateLocalPreviewHandler:
    def __init__(
        self,
        repository: LocalPreviewRepository,
        fingerprint: RequestFingerprint,
    ) -> None:
        self.repository = repository
        self.fingerprint = fingerprint

    async def execute(self, message: CreateLocalPreview) -> tuple[WorkloadDetails, bool]:
        request = message.request
        return await self.repository.create_local_preview(
            message.access,
            request,
            message.idempotency_key,
            self.fingerprint.for_value(request),
            message.now,
        )
