"""Declarative bindings; this is the only layer selecting concrete implementations."""

from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devops_platform.application.applications.read_templates.handler import (
    ReadTemplatesHandler,
)
from devops_platform.application.interfaces.applications import (
    ApplicationCreationRepository,
    ApplicationReadRepository,
)
from devops_platform.application.interfaces.software_delivery import (
    ApplicationDatabaseBindingResolver,
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
from devops_platform.infra.composition.application_bindings import (
    SQLAlchemyApplicationDatabaseBindings,
)
from devops_platform.infra.persistence.repositories.delivery import (
    SQLAlchemyApplicationDeliveryRepository,
)
from devops_platform.infra.providers.docker_application import DockerApplicationAdapter
from devops_platform.infra.providers.github import GitHubRepositoryAdapter
from devops_platform.infra.security.approval import StaticApprovedImageCatalog
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher
from devops_platform.infra.security.fingerprint import Sha256RequestFingerprint
from devops_platform.infra.security.webhooks import HmacGitHubWebhookVerifier
from devops_platform.infra.templates.catalog import FilesystemTemplateCatalog
from shared.infra.settings import Settings


class ApplicationDeliveryProvider(Provider):
    read_templates_handler = provide(ReadTemplatesHandler, scope=Scope.REQUEST)

    @provide(scope=Scope.APP)
    def templates(self, settings: Settings) -> FilesystemTemplateCatalog:
        template_root = (
            Path(settings.template_root)
            if settings.template_root is not None
            else Path(str(files("devops_platform.infra.templates") / "catalogs"))
        )
        return FilesystemTemplateCatalog(template_root)

    @provide(scope=Scope.APP)
    def template_catalog(self, templates: FilesystemTemplateCatalog) -> TemplateCatalog:
        return templates

    @provide(scope=Scope.APP)
    def images(self, settings: Settings) -> StaticApprovedImageCatalog:
        return StaticApprovedImageCatalog({"local": frozenset(settings.approved_local_images)})

    @provide(scope=Scope.APP)
    def repository_provisioner(self, settings: Settings) -> GitHubRepositoryAdapter | None:
        if settings.github_organization is None or settings.github_token is None:
            return None
        return GitHubRepositoryAdapter(
            settings.github_organization,
            settings.github_token.get_secret_value(),
            settings.github_api_url,
        )

    @provide(scope=Scope.APP)
    def database_bindings(
        self, settings: Settings, sessions: async_sessionmaker[AsyncSession]
    ) -> ApplicationDatabaseBindingResolver | None:
        if settings.installation_id is None or settings.resource_key is None:
            return None
        cipher = FernetResourceCredentialCipher(
            settings.resource_key.get_secret_value(), settings.resource_key_id
        )
        return SQLAlchemyApplicationDatabaseBindings(sessions, settings.installation_id, cipher)

    @provide(scope=Scope.APP)
    def deployer(
        self,
        settings: Settings,
        bindings: ApplicationDatabaseBindingResolver | None,
    ) -> DockerApplicationAdapter | None:
        if not settings.approved_local_images or settings.installation_id is None:
            return None
        return DockerApplicationAdapter(
            frozenset(settings.approved_local_images),
            settings.docker_url,
            settings.postgres_image,
            settings.installation_id,
            bindings,
        )

    @provide(scope=Scope.REQUEST)
    def delivery_repository(self, session: AsyncSession) -> SQLAlchemyApplicationDeliveryRepository:
        return SQLAlchemyApplicationDeliveryRepository(session)

    @provide(scope=Scope.REQUEST)
    def application_creation_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationCreationRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def local_preview_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> LocalPreviewRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def application_read_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationReadRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def application_attachment_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationResourceAttachmentRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def application_deployment_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> ApplicationDeploymentRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def delivery_retry_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> DeliveryRetryRepository:
        return repository

    @provide(scope=Scope.REQUEST)
    def preview_webhook_repository(
        self, repository: SQLAlchemyApplicationDeliveryRepository
    ) -> PreviewWebhookRepository:
        return repository

    @provide(scope=Scope.APP)
    def request_fingerprint(self) -> RequestFingerprint:
        return Sha256RequestFingerprint()

    @provide(scope=Scope.APP)
    def webhook_verifier(self, settings: Settings) -> WebhookSignatureVerifier | None:
        if settings.github_webhook_secret is None:
            return None
        return HmacGitHubWebhookVerifier(settings.github_webhook_secret.get_secret_value())

    @provide(scope=Scope.REQUEST)
    def approved_image_catalog(self, images: StaticApprovedImageCatalog) -> ApprovedImageCatalog:
        return images
