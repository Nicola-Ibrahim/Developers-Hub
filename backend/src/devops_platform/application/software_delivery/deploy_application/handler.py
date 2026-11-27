"""Queue an approved immutable image for application deployment."""

from devops_platform.application.interfaces.software_delivery import (
    ApplicationDeploymentRepository,
    ApprovedImageCatalog,
    RequestFingerprint,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
)
from devops_platform.application.software_delivery.shared.models import DeploymentDetails


class DeployApplicationHandler:
    def __init__(
        self,
        repository: ApplicationDeploymentRepository,
        images: ApprovedImageCatalog,
        fingerprint: RequestFingerprint,
    ) -> None:
        self.repository, self.images = repository, images
        self.fingerprint = fingerprint

    async def execute(self, message: DeployApplication) -> DeploymentDetails:
        access, application_id, command = message.access, message.application_id, message.request
        if not self.images.is_approved(command.image_digest, command.target_id):
            raise PlatformRequestError(
                "image_not_approved", "Image is not approved for this target", 403
            )
        return await self.repository.enqueue_deployment(
            access,
            application_id,
            command,
            message.idempotency_key,
            self.fingerprint.for_value(command),
            message.now,
        )
