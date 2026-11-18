"""Dependency bindings for cross-context application bridges."""

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from composition.integrations.application_resources import LedgerApplicationResources
from composition.integrations.first_admin_unit_of_work import FirstAdminUnitOfWork
from composition.integrations.project_access_persistence import (
    identity_repository_for_session,
    project_access_repository_for_session,
)
from composition.integrations.project_registration import RegisterProjectCommandHandler
from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.application.interfaces.software_delivery import ResourceProvisioner
from devops_platform.application.projects.handler import RegisterProjectHandler
from devops_platform.application.resource_management.catalog.catalog import ApprovedPostgresCatalog
from devops_platform.domain.interfaces.project_access_directory import ProjectAccessDirectory
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.infra.composition.browser_transactions import SqlAlchemyIdentityTransaction
from shared.application.interfaces.unit_of_work import UnitOfWork
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings


class CrossContextIntegrationProvider(Provider):
    """Bind adapters that coordinate identity and developer-platform capabilities."""

    @provide(scope=Scope.REQUEST, provides=ProjectAccessRepository)
    def project_access_repository(self, session: AsyncSession) -> ProjectAccessRepository:
        return project_access_repository_for_session(session)

    @provide(scope=Scope.REQUEST, provides=UnitOfWork)
    def first_admin_unit_of_work(self, unit: SqlAlchemyUnitOfWork) -> UnitOfWork:
        return FirstAdminUnitOfWork(unit)

    @provide(scope=Scope.REQUEST, provides=BrowserTransaction)
    def browser_transaction(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyIdentityTransaction:
        return SqlAlchemyIdentityTransaction(sessions, identity_repository_for_session)

    @provide(scope=Scope.APP)
    def application_resources(
        self,
        sessions: async_sessionmaker[AsyncSession],
        catalog: ApprovedPostgresCatalog,
        settings: Settings,
    ) -> ResourceProvisioner:
        return LedgerApplicationResources(sessions, catalog, settings.installation_id)

    @provide(scope=Scope.REQUEST)
    def register_project(
        self,
        directory: ProjectAccessDirectory,
        register: RegisterProjectHandler,
        unit: SqlAlchemyUnitOfWork,
    ) -> RegisterProjectCommandHandler:
        return RegisterProjectCommandHandler(directory, register, unit)
