"""Per-dispatch Platform bindings isolated to Dishka's ACTION component."""

import hashlib
import json
from dataclasses import asdict
from typing import Annotated

from dishka import FromComponent, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devops_platform.application.interfaces.applications import (
    ApplicationCreationRepository,
    ApplicationReadRepository,
)
from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.interfaces.resources import (
    ResourceCredentialCipher,
    ResourceRepository,
)
from devops_platform.application.interfaces.software_delivery import (
    ApplicationDeploymentRepository,
    ApplicationResourceAttachmentRepository,
    ApprovedImageCatalog,
    DeliveryRetryRepository,
    LocalPreviewRepository,
    PreviewWebhookRepository,
    RequestFingerprint,
    TemplateCatalog,
    WebhookSignatureVerifier,
)
from devops_platform.application.resource_management.catalog.catalog import ApprovedPostgresCatalog
from devops_platform.application.resource_management.catalog.handler import ReadCatalogQueryHandler
from devops_platform.application.resource_management.submit_database_request.command import (
    DatabaseRequest,
)
from devops_platform.application.resource_management.submit_database_request.handler import (
    RequestTemporaryDatabaseHandler,
)
from devops_platform.application.software_delivery.handle_preview_webhook.handler import (
    ProcessGithubPreviewWebhookHandler,
)
from devops_platform.infra.composition.module import (
    PLATFORM_HANDLER_REGISTRY,
)
from devops_platform.infra.persistence.repositories.delivery import (
    SQLAlchemyApplicationDeliveryRepository,
)
from devops_platform.infra.persistence.repositories.project_registration import (
    SQLAlchemyProjectRegistrationRepository,
)
from devops_platform.infra.persistence.repositories.resource import SQLAlchemyResourceRepository
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher
from shared.infra.dispatch import register_handlers
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings


class PlatformActionProvider(Provider):
    """Create the Platform session and all session-bound adapters per dispatch."""

    def __init__(self, *, component: str) -> None:
        super().__init__(component=component)
        register_handlers(
            self,
            PLATFORM_HANDLER_REGISTRY,
            scope=Scope.ACTION,
            factories={
                ReadCatalogQueryHandler: self.catalog_handler,
                RequestTemporaryDatabaseHandler: self.request_handler,
                ProcessGithubPreviewWebhookHandler: self.process_preview_webhook_handler,
            },
        )

    @provide(scope=Scope.ACTION)
    def session(
        self,
        sessions: Annotated[async_sessionmaker[AsyncSession], FromComponent("")],
    ) -> AsyncSession:
        return sessions()

    unit_of_work = provide(SqlAlchemyUnitOfWork, scope=Scope.ACTION)

    @provide(scope=Scope.ACTION, provides=ProjectRegistrationRepository)
    def project_registration_repository(
        self, session: AsyncSession
    ) -> ProjectRegistrationRepository:
        return SQLAlchemyProjectRegistrationRepository(session)

    @provide(scope=Scope.ACTION, provides=ResourceRepository)
    def resource_repository(self, session: AsyncSession) -> ResourceRepository:
        return SQLAlchemyResourceRepository(session)

    delivery_repository = provide(SQLAlchemyApplicationDeliveryRepository, scope=Scope.ACTION)

    @provide(scope=Scope.ACTION, provides=ApplicationCreationRepository)
    def application_creation_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationCreationRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=LocalPreviewRepository)
    def local_preview_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> LocalPreviewRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=ApplicationReadRepository)
    def application_read_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationReadRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=ApplicationResourceAttachmentRepository)
    def application_attachment_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationResourceAttachmentRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=ApplicationDeploymentRepository)
    def application_deployment_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationDeploymentRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=DeliveryRetryRepository)
    def delivery_retry_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> DeliveryRetryRepository:
        return repository

    @provide(scope=Scope.ACTION, provides=PreviewWebhookRepository)
    def preview_webhook_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> PreviewWebhookRepository:
        return repository

    @provide(scope=Scope.ACTION)
    def approved_catalog(
        self, catalog: Annotated[ApprovedPostgresCatalog, FromComponent("")]
    ) -> ApprovedPostgresCatalog:
        return catalog

    @provide(scope=Scope.ACTION)
    def template_catalog(
        self, catalog: Annotated[TemplateCatalog, FromComponent("")]
    ) -> TemplateCatalog:
        return catalog

    @provide(scope=Scope.ACTION)
    def approved_image_catalog(
        self, catalog: Annotated[ApprovedImageCatalog, FromComponent("")]
    ) -> ApprovedImageCatalog:
        return catalog

    @provide(scope=Scope.ACTION)
    def webhook_verifier(
        self, verifier: Annotated[WebhookSignatureVerifier | None, FromComponent("")]
    ) -> WebhookSignatureVerifier | None:
        return verifier

    @provide(scope=Scope.ACTION)
    def request_fingerprint(
        self, fingerprint: Annotated[RequestFingerprint, FromComponent("")]
    ) -> RequestFingerprint:
        return fingerprint

    @provide(scope=Scope.ACTION)
    def credential_cipher(
        self, settings: Annotated[Settings, FromComponent("")]
    ) -> ResourceCredentialCipher | None:
        if settings.resource_key is None:
            return None
        return FernetResourceCredentialCipher(
            settings.resource_key.get_secret_value(), settings.resource_key_id
        )

    def catalog_handler(self, catalog: ApprovedPostgresCatalog) -> ReadCatalogQueryHandler:
        return ReadCatalogQueryHandler(catalog)

    def request_handler(
        self,
        repository: ResourceRepository,
        catalog: ApprovedPostgresCatalog,
        settings: Annotated[Settings, FromComponent("")],
    ) -> RequestTemporaryDatabaseHandler:
        def fingerprint(command: DatabaseRequest) -> str:
            payload = json.dumps(
                asdict(command), sort_keys=True, separators=(",", ":"), default=str
            )
            return hashlib.sha256(payload.encode()).hexdigest()

        return RequestTemporaryDatabaseHandler(
            repository, catalog, fingerprint, settings.installation_id
        )

    def process_preview_webhook_handler(
        self,
        repository: PreviewWebhookRepository,
        images: ApprovedImageCatalog,
        verifier: WebhookSignatureVerifier | None,
        settings: Annotated[Settings, FromComponent("")],
    ) -> ProcessGithubPreviewWebhookHandler:
        return ProcessGithubPreviewWebhookHandler(
            repository,
            images,
            verifier,
            settings.github_allowed_repository_owner,
            settings.preview_owner_id,
            settings.preview_ttl_seconds,
        )
