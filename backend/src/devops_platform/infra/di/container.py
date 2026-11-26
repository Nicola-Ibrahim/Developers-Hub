"""Developer Platform-owned registrations for API and worker processes."""

from dishka import Provider

from devops_platform import application
from devops_platform.application.project_access.bootstrap_first_admin.command import (
    BootstrapFirstAdmin,
)
from devops_platform.infra.di.providers_action import PlatformActionProvider
from devops_platform.infra.di.providers_delivery import ApplicationDeliveryProvider
from devops_platform.infra.di.providers_platform import PlatformProvider
from devops_platform.infra.di.providers_worker import ApplicationWorkerProvider
from devops_platform.infra.handlers import PLATFORM_HANDLER_REGISTRY
from shared.infra.dispatch import validate_context_messages


class DeveloperPlatformContainer:
    """Keep Platform DI registrations with the bounded context that owns them."""

    def providers(self) -> tuple[Provider, ...]:
        validate_context_messages(
            PLATFORM_HANDLER_REGISTRY, application, internal=(BootstrapFirstAdmin,)
        )
        return (
            PlatformProvider(),
            PlatformActionProvider(component="platform_action"),
            ApplicationDeliveryProvider(),
        )

    def worker_providers(self) -> tuple[Provider, ...]:
        return (ApplicationWorkerProvider(),)
