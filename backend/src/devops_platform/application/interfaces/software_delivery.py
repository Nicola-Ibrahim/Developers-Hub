"""Application contracts grouped by capability."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.software_delivery.attach_database.command import (
    ResourceAttachmentSpec,
)
from devops_platform.application.software_delivery.create_local_preview.command import (
    LocalPreviewRegistration,
)
from devops_platform.application.software_delivery.deploy_application.command import (
    DeploymentSpec,
)
from devops_platform.application.software_delivery.shared.database_binding import (
    ApplicationDatabaseBinding,
)
from devops_platform.application.software_delivery.shared.models import (
    DeliveryClaim,
    DeliveryResult,
    DeliveryStepDetails,
    DeploymentDetails,
    RegisteredRepository,
    WorkloadDetails,
)
from devops_platform.application.software_delivery.shared.models import (
    GeneratedFile as GeneratedFile,
)
from devops_platform.application.software_delivery.shared.models import (
    TemplateVersion as TemplateVersion,
)
from devops_platform.application.software_delivery.shared.models import (
    WebhookResult as WebhookResult,
)

"""Persistence required to attach a resource request to an application."""


class ApplicationResourceAttachmentRepository(ABC):
    @abstractmethod
    async def enqueue_resource_attachment(
        self,
        access: AccessContext,
        application_id: UUID,
        command: ResourceAttachmentSpec,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> DeliveryStepDetails: ...


class LocalPreviewRepository(ABC):
    @abstractmethod
    async def create_local_preview(
        self,
        access: AccessContext,
        command: LocalPreviewRegistration,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> tuple[WorkloadDetails, bool]: ...


"""Persistence required to queue an application deployment."""


class ApplicationDeploymentRepository(ABC):
    @abstractmethod
    async def enqueue_deployment(
        self,
        access: AccessContext,
        application_id: UUID,
        command: DeploymentSpec,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> DeploymentDetails: ...


"""Durable queue operations for delivery workers."""


class DeliveryWorkQueue(ABC):
    @abstractmethod
    async def claim_step(self, now: datetime, lease_seconds: int) -> DeliveryClaim | None: ...
    @abstractmethod
    async def heartbeat_step(
        self, claim: DeliveryClaim, now: datetime, lease_seconds: int
    ) -> bool: ...
    @abstractmethod
    async def complete_step(
        self, claim: DeliveryClaim, result: DeliveryResult, now: datetime
    ) -> bool: ...
    @abstractmethod
    async def fail_step(
        self,
        claim: DeliveryClaim,
        error_code: str,
        now: datetime,
        retry_after_seconds: int,
        retryable: bool,
    ) -> bool: ...
    @abstractmethod
    async def effect_is_current(self, claim: DeliveryClaim, now: datetime) -> bool: ...


"""Persistence required for preview-webhook idempotency and lifecycle."""


class PreviewWebhookRepository(ABC):
    @abstractmethod
    async def record_webhook(
        self,
        *,
        delivery_id: str,
        payload_hash: str,
        event: str,
        repository: str,
        pull_request: int | None,
        action: str,
        now: datetime,
    ) -> bool: ...
    @abstractmethod
    async def find_registered_repository(self, repository: str) -> RegisteredRepository | None: ...
    @abstractmethod
    async def request_preview(
        self,
        *,
        project_id: UUID,
        owner_id: UUID,
        repository: str,
        pull_request: int,
        branch: str,
        head_sha: str,
        image_digest: str | None,
        template_id: str,
        template_version: str,
        ttl_seconds: int,
        now: datetime,
    ) -> UUID | None: ...
    @abstractmethod
    async def close_preview(self, *, repository: str, pull_request: int, now: datetime) -> int: ...
    @abstractmethod
    async def expire_previews(self, now: datetime, limit: int) -> int: ...


"""Persistence required to retry a delivery step."""


class DeliveryRetryRepository(ABC):
    @abstractmethod
    async def retry_step(
        self, access: AccessContext, workload_id: UUID, step_id: UUID, now: datetime
    ) -> DeliveryStepDetails: ...


"""Application generation and delivery workflows, expressed as repository/provider ports."""


class TemplateCatalog(ABC):
    @abstractmethod
    def list_templates(self) -> tuple[TemplateVersion, ...]: ...

    @abstractmethod
    def get(self, template_id: str, version: str) -> TemplateVersion: ...

    @abstractmethod
    def render(
        self, template_id: str, version: str, values: dict[str, str]
    ) -> tuple[GeneratedFile, ...]: ...


class WebhookSignatureVerifier(ABC):
    """Verifies a provider signature and parses its authenticated JSON payload."""

    @abstractmethod
    def verify(self, raw_body: bytes, signature: str | None) -> tuple[dict[str, object], str]: ...


class RequestFingerprint(ABC):
    @abstractmethod
    def for_value(self, value: object) -> str: ...


class RepositoryProvisioner(ABC):
    @abstractmethod
    async def create_repository(
        self,
        *,
        project_id: UUID,
        application_id: UUID,
        name: str,
        template: TemplateVersion,
        files: tuple[GeneratedFile, ...],
        idempotency_key: str,
    ) -> str: ...

    @abstractmethod
    async def create_update_pull_request(
        self,
        *,
        repository_url: str,
        branch: str,
        files: tuple[GeneratedFile, ...],
        idempotency_key: str,
    ) -> str: ...


class ResourceProvisioner(ABC):
    @abstractmethod
    async def request(
        self,
        *,
        project_id: UUID,
        environment_id: UUID,
        owner_id: UUID,
        command: ResourceAttachmentSpec,
        idempotency_key: str,
    ) -> UUID: ...

    @abstractmethod
    async def ready(self, project_id: UUID, resource_id: UUID) -> bool: ...

    @abstractmethod
    async def delete(
        self, project_id: UUID, owner_id: UUID, resource_id: UUID, idempotency_key: str
    ) -> None: ...


class ApplicationDeployer(ABC):
    @abstractmethod
    async def deploy(
        self,
        *,
        project_id: UUID,
        application_id: UUID,
        deployment_id: UUID,
        image_digest: str,
        target_id: str,
        resource_id: UUID | None,
        idempotency_key: str,
    ) -> tuple[str, str]: ...

    @abstractmethod
    async def remove(
        self, project_id: UUID, application_id: UUID, idempotency_key: str
    ) -> None: ...


class WorkloadDeliveryFailure(Exception):
    def __init__(self, code: str, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else "delivery_failed"
        self.retryable = retryable


class ApprovedImageCatalog(ABC):
    @abstractmethod
    def is_approved(self, digest: str, target_id: str) -> bool: ...


ApplicationDeliveryFailure = WorkloadDeliveryFailure


class ApplicationDatabaseBindingResolver(ABC):
    @abstractmethod
    async def resolve(
        self, project_id: UUID, application_id: UUID, resource_id: UUID
    ) -> ApplicationDatabaseBinding: ...
