"""Assemble and run the dependency graph for a backend process."""

import asyncio
from typing import Literal

from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.health.metrics import OperationalMetrics
from api.health.metrics_adapter import DatabaseOperationalMetrics
from api.settings.config import BrowserCookiePolicy
from devops_platform.application.interfaces.project_access import ProjectAccessRepository
from devops_platform.authorization import ALL_SCOPES
from devops_platform.infra.di.container import DeveloperPlatformContainer
from devops_platform.infra.persistence.repositories.project_access import (
    SQLAlchemyProjectAccessRepository,
    SQLAlchemyProjectAccessRules,
)
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.infra.di.container import IdentityContainer
from identity.infra.di.providers import IdentityTokenScopePolicy
from identity.infra.persistence.api_token_transactions import SqlAlchemyApiTokenTransaction
from identity.infra.persistence.identity_transactions import SqlAlchemyIdentityTransaction
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.persistence.repositories.sessions import identity_repositories_for_session
from shared.authorization.credentials import RequestCredentials
from shared.infra.authorization.provider import AuthorizationProvider
from shared.infra.providers import DatabaseProvider, ExternalDatabase
from shared.infra.settings import Settings


class RuntimeContext(Provider):
    settings = from_context(Settings, scope=Scope.APP)
    database = from_context(ExternalDatabase, scope=Scope.APP)
    identity_token_scopes = from_context(IdentityTokenScopePolicy, scope=Scope.APP)

    @provide(scope=Scope.REQUEST)
    def request_credentials(self) -> RequestCredentials:
        return RequestCredentials()


class HttpProvider(Provider):
    metrics = provide(DatabaseOperationalMetrics, provides=OperationalMetrics, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def browser_cookie_policy(self, settings: Settings) -> BrowserCookiePolicy:
        return BrowserCookiePolicy(
            secure=settings.cookie_secure,
            allowed_origins=settings.browser_allowed_origins,
        )


class ProjectAccessProvider(Provider):
    """Bind Platform membership persistence and Identity audit on one SQL session."""

    @provide
    def project_access_repository(self, session: AsyncSession) -> ProjectAccessRepository:
        access = SQLAlchemyProjectAccessRules(session)
        _, activity = identity_repositories_for_session(session, access)
        return SQLAlchemyProjectAccessRepository(
            session=session,
            rules=access,
            user_row=InternalUserRow,
            record_activity=activity.record_project_access_activity,
            validation_error=IdentityValidationError,
        )


class IdentityTransactionsProvider(Provider):
    access = provide(
        SQLAlchemyProjectAccessRules, provides=IdentityProjectAccess, scope=Scope.REQUEST
    )

    @provide(scope=Scope.REQUEST)
    def browser_transaction(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> IdentityTransaction:
        return SqlAlchemyIdentityTransaction(
            sessions,
            lambda session: identity_repositories_for_session(
                session, SQLAlchemyProjectAccessRules(session)
            ),
        )

    @provide(scope=Scope.REQUEST)
    def api_token_transaction(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> ApiTokenTransaction:
        return SqlAlchemyApiTokenTransaction(
            sessions,
            lambda session: SQLAlchemyApiTokenRepository(
                session, SQLAlchemyProjectAccessRules(session)
            ),
        )


class IdentityActionProvider(Provider):
    access = provide(
        SQLAlchemyProjectAccessRules, provides=IdentityProjectAccess, scope=Scope.ACTION
    )
    tokens = provide(SQLAlchemyApiTokenRepository, provides=ApiTokenRepository, scope=Scope.ACTION)


class BackendContainer:
    """Build API, worker, or combined containers from supplied runtime dependencies.

    Contexts contribute providers to this process container instead of creating
    isolated Dishka containers. The shared SQL session and unit of work must remain
    in one container so cross-context operations keep one transaction boundary.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
        overrides: tuple[Provider, ...] = (),
    ) -> None:
        self._settings = settings
        self._database = ExternalDatabase(engine)
        self._overrides = overrides
        self._identity = IdentityContainer(tuple(ALL_SCOPES))
        self._platform = DeveloperPlatformContainer()

    def api(self) -> AsyncContainer:
        return self._compose(HttpProvider(), FastapiProvider())

    def worker(self) -> AsyncContainer:
        return self._compose(*self._platform.worker_providers())

    def combined(self) -> AsyncContainer:
        return self._compose(
            HttpProvider(),
            FastapiProvider(),
            *self._platform.worker_providers(),
        )

    def _compose(self, *host_providers: Provider) -> AsyncContainer:
        context: dict[type[object], object] = {
            Settings: self._settings,
            ExternalDatabase: self._database,
        }
        context.update(self._identity.context())
        return make_async_container(
            RuntimeContext(),
            ProjectAccessProvider(scope=Scope.REQUEST),
            ProjectAccessProvider(scope=Scope.ACTION, component="platform_action"),
            IdentityTransactionsProvider(),
            IdentityActionProvider(component="identity_action"),
            DatabaseProvider(),
            AuthorizationProvider(),
            *self._identity.providers(),
            *self._platform.providers(),
            *host_providers,
            *self._overrides,
            context=context,
            lock_factory=asyncio.Lock,
        )


class BackendRuntime:
    """Own startup and shutdown for an API or worker process."""

    def __init__(
        self,
        settings: Settings | None,
        *,
        engine: AsyncEngine | None = None,
        container: AsyncContainer | None = None,
        process: Literal["api", "worker"] = "api",
    ) -> None:
        if container is None:
            containers = BackendContainer(
                settings if settings is not None else Settings(),  # type: ignore[call-arg]
                engine=engine,
            )
            self.container = containers.api() if process == "api" else containers.worker()
        else:
            self.container = container
        self._owns_container = container is None

    async def start(self) -> None:
        """Initialize owned backend resources without connecting or applying migrations."""
        if self._owns_container:
            # Creating an AsyncEngine is lazy: it builds the pool configuration but
            # does not open a database connection. The provider owns its shutdown.
            await self.container.get(AsyncEngine)

    async def close(self) -> None:
        if self._owns_container:
            await self.container.close()
