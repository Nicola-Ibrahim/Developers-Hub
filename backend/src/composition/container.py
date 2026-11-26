"""Compose one process container from shared services and context-owned registrations."""

import asyncio

from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from sqlalchemy.ext.asyncio import AsyncEngine

from api.health.metrics import OperationalMetrics
from api.health.metrics_adapter import DatabaseOperationalMetrics
from api.settings.config import BrowserCookiePolicy
from composition.integrations.providers import (
    CrossContextIntegrationProvider,
    IdentityActionIntegrationProvider,
    PlatformActionIntegrationProvider,
)
from devops_platform.authorization import ALL_SCOPES
from devops_platform.infra.composition.container import DeveloperPlatformContainer
from identity.infra.composition.container import IdentityContainer
from identity.infra.composition.providers import IdentityTokenScopePolicy
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
            CrossContextIntegrationProvider(),
            IdentityActionIntegrationProvider(component="identity_action"),
            PlatformActionIntegrationProvider(component="platform_action"),
            DatabaseProvider(),
            AuthorizationProvider(),
            *self._identity.providers(),
            *self._platform.providers(),
            *host_providers,
            *self._overrides,
            context=context,
            lock_factory=asyncio.Lock,
        )
