from devops_platform.application.interfaces.software_delivery import (
    LocalPreviewRepository,
    RequestFingerprint,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.create_local_preview.command import (
    CreateLocalPreview,
)
from devops_platform.application.software_delivery.shared.models import WorkloadDetails
from devops_platform.application.software_delivery.shared.policy import (
    APP_NAME,
    validate_delivery_key,
)


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
        validate_delivery_key(message.idempotency_key)
        if not APP_NAME.fullmatch(request.name):
            raise PlatformRequestError("invalid_workload_name", "Workload name is invalid", 422)
        if not 60 <= request.ttl_seconds <= 86400:
            raise PlatformRequestError("invalid_lease", "Preview lifetime is outside policy", 422)
        return await self.repository.create_local_preview(
            message.access,
            request,
            message.idempotency_key,
            self.fingerprint.for_value(request),
            message.now,
        )
