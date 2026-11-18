"""Declarative bindings; this is the only layer selecting concrete implementations."""

import hashlib
import json
from dataclasses import asdict

from dishka import Provider, Scope, provide

from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.application.interfaces.projects import ProjectRegistrationRepository
from devops_platform.application.interfaces.resources import (
    ResourceCredentialCipher,
    ResourceRepository,
)
from devops_platform.application.project_access.bootstrap_first_admin.handler import (
    BootstrapFirstAdminHandler,
)
from devops_platform.application.project_access.list_project_members.handler import (
    ListProjectMembersHandler,
)
from devops_platform.application.project_access.manage_project_membership.handler import (
    ManageProjectMembershipHandler,
)
from devops_platform.application.projects.get_project.handler import (
    ReadProjectHandler,
)
from devops_platform.application.projects.handler import RegisterProjectHandler
from devops_platform.application.projects.list_projects.handler import (
    ReadProjectsHandler,
)
from devops_platform.application.resource_management.catalog.catalog import ApprovedPostgresCatalog
from devops_platform.application.resource_management.catalog.handler import ReadCatalogQueryHandler
from devops_platform.application.resource_management.delete_database.handler import (
    DeleteTemporaryDatabaseHandler,
)
from devops_platform.application.resource_management.get_operation.handler import (
    ReadOperationHandler,
)
from devops_platform.application.resource_management.get_resource.handler import (
    ReadResourceHandler,
)
from devops_platform.application.resource_management.list_resources.handler import (
    ReadResourcesHandler,
)
from devops_platform.application.resource_management.read_activity.handler import (
    ListResourceActivityQueryHandler,
)
from devops_platform.application.resource_management.read_connection.handler import (
    GetDatabaseConnectionQueryHandler,
)
from devops_platform.application.resource_management.renew_lease.handler import (
    RenewDatabaseLeaseHandler,
)
from devops_platform.application.resource_management.submit_database_request.command import (
    DatabaseRequest,
)
from devops_platform.application.resource_management.submit_database_request.handler import (
    RequestTemporaryDatabaseHandler,
)
from devops_platform.domain.interfaces.project_access_directory import ProjectAccessDirectory
from devops_platform.infra.persistence.repositories.project_access_directory import (
    SQLAlchemyProjectAccessDirectory,
)
from devops_platform.infra.persistence.repositories.project_registration import (
    SQLAlchemyProjectRegistrationRepository,
)
from devops_platform.infra.persistence.repositories.resource import SQLAlchemyResourceRepository
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher
from shared.infra.settings import Settings


class PlatformProvider(Provider):
    project_access_directory = provide(
        SQLAlchemyProjectAccessDirectory,
        provides=ProjectAccessDirectory,
        scope=Scope.REQUEST,
    )
    list_project_members = provide(ListProjectMembersHandler, scope=Scope.REQUEST)
    bootstrap_first_admin = provide(BootstrapFirstAdminHandler, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def manage_project_membership(
        self, repository: ProjectAccessRepository
    ) -> ManageProjectMembershipHandler:
        return ManageProjectMembershipHandler(repository)

    project_handler = provide(ReadProjectHandler, scope=Scope.REQUEST)
    projects_handler = provide(ReadProjectsHandler, scope=Scope.REQUEST)
    resources_handler = provide(ReadResourcesHandler, scope=Scope.REQUEST)
    resource_handler = provide(ReadResourceHandler, scope=Scope.REQUEST)
    operation_handler = provide(ReadOperationHandler, scope=Scope.REQUEST)
    renew_handler = provide(RenewDatabaseLeaseHandler, scope=Scope.REQUEST)
    delete_handler = provide(DeleteTemporaryDatabaseHandler, scope=Scope.REQUEST)
    connection_handler = provide(GetDatabaseConnectionQueryHandler, scope=Scope.REQUEST)
    activity_handler = provide(ListResourceActivityQueryHandler, scope=Scope.REQUEST)
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

    register = provide(RegisterProjectHandler, scope=Scope.REQUEST)

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

    @provide(scope=Scope.REQUEST)
    def catalog(self, catalog: ApprovedPostgresCatalog) -> ReadCatalogQueryHandler:
        return ReadCatalogQueryHandler(catalog)

    @provide(scope=Scope.REQUEST)
    def request(
        self,
        repository: ResourceRepository,
        catalog: ApprovedPostgresCatalog,
        settings: Settings,
    ) -> RequestTemporaryDatabaseHandler:
        def fingerprint(command: DatabaseRequest) -> str:
            payload = json.dumps(
                asdict(command), sort_keys=True, separators=(",", ":"), default=str
            )
            return hashlib.sha256(payload.encode()).hexdigest()

        return RequestTemporaryDatabaseHandler(
            repository, catalog, fingerprint, settings.installation_id
        )
