"""Declarative bindings; this is the only layer selecting concrete implementations."""

from dishka import Provider, Scope, provide

from devops_platform.application.interfaces.module import DeveloperPlatformModule as PlatformModule
from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.interfaces.resources import (
    ResourceCredentialCipher,
    ResourceRepository,
)
from devops_platform.application.project_access.bootstrap_first_admin.handler import (
    BootstrapFirstAdminHandler,
)
from devops_platform.application.projects.handler import RegisterProjectHandler
from devops_platform.application.resource_management.catalog.catalog import ApprovedPostgresCatalog
from devops_platform.domain.interfaces.project_access_directory import ProjectAccessDirectory
from devops_platform.infra.module import DeveloperPlatformModule
from devops_platform.infra.persistence.repositories.project_access_directory import (
    SQLAlchemyProjectAccessDirectory,
)
from devops_platform.infra.persistence.repositories.project_registration import (
    SQLAlchemyProjectRegistrationRepository,
)
from devops_platform.infra.persistence.repositories.resource import SQLAlchemyResourceRepository
from devops_platform.infra.project_registration import (
    ProjectUnitOfWork,
    RegisterProjectCommandHandler,
)
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher
from shared.application.interfaces.unit_of_work import UnitOfWork
from shared.infra.settings import Settings


class PlatformProvider(Provider):
    platform = provide(DeveloperPlatformModule, provides=PlatformModule, scope=Scope.REQUEST)

    project_access_directory = provide(
        SQLAlchemyProjectAccessDirectory,
        provides=ProjectAccessDirectory,
        scope=Scope.REQUEST,
    )
    bootstrap_first_admin = provide(BootstrapFirstAdminHandler, scope=Scope.REQUEST)

    project_registration_repository = provide(
        SQLAlchemyProjectRegistrationRepository,
        provides=ProjectRegistrationRepository,
        scope=Scope.REQUEST,
    )
    resource_repository = provide(
        SQLAlchemyResourceRepository,
        provides=ResourceRepository,
        scope=Scope.REQUEST,
    )

    project_unit = provide(ProjectUnitOfWork, provides=UnitOfWork, scope=Scope.REQUEST)
    register = provide(RegisterProjectHandler, scope=Scope.REQUEST)
    register_project = provide(RegisterProjectCommandHandler, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def credential_cipher(self, settings: Settings) -> ResourceCredentialCipher | None:
        if settings.resource_key is None:
            return None
        return FernetResourceCredentialCipher(
            settings.resource_key.get_secret_value(), settings.resource_key_id
        )

    @provide(scope=Scope.APP)
    def approved_catalog(self, settings: Settings) -> ApprovedPostgresCatalog:
        # Register the planned option without claiming an implemented provider.
        from devops_platform.application.resource_management.catalog.models import PostgresOption

        enabled = (
            settings.local_provider_enabled
            and settings.resource_key is not None
            and settings.installation_id is not None
        )
        return ApprovedPostgresCatalog(
            (
                PostgresOption(
                    requestable=enabled,
                    unavailable_reason=None if enabled else "provider_not_enabled",
                ),
            )
        )
