"""Explicit platform message bindings; use-case adapters stay in this context."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from devops_platform.application.applications.create_application.command import (
    CreateApplication,
)
from devops_platform.application.applications.create_application.handler import (
    CreateApplicationHandler,
)
from devops_platform.application.applications.read_applications.handler import (
    ReadApplicationHandler,
    ReadApplicationsHandler,
    ReadDeploymentHistoryHandler,
)
from devops_platform.application.applications.read_applications.query import (
    ReadApplication,
    ReadApplications,
    ReadDeploymentHistory,
)
from devops_platform.application.applications.read_templates.handler import (
    ReadTemplatesHandler,
)
from devops_platform.application.applications.read_templates.query import ReadTemplates
from devops_platform.application.resource_management.catalog.handler import ReadCatalogQueryHandler
from devops_platform.application.resource_management.catalog.query import ReadCatalog
from devops_platform.application.resource_management.delete_database.command import (
    DeleteDatabase,
)
from devops_platform.application.resource_management.delete_database.handler import (
    DeleteTemporaryDatabaseHandler,
)
from devops_platform.application.resource_management.read_activity.handler import (
    ListResourceActivityQueryHandler,
)
from devops_platform.application.resource_management.read_activity.query import (
    ReadResourceActivity,
)
from devops_platform.application.resource_management.read_connection.handler import (
    GetDatabaseConnectionQueryHandler,
)
from devops_platform.application.resource_management.read_connection.query import (
    ReadDatabaseConnection,
)
from devops_platform.application.resource_management.read_resources.handler import (
    ReadOperationHandler,
    ReadProjectHandler,
    ReadProjectsHandler,
    ReadResourceHandler,
    ReadResourcesHandler,
)
from devops_platform.application.resource_management.read_resources.query import (
    ReadOperation,
    ReadProject,
    ReadProjects,
    ReadResource,
    ReadResources,
)
from devops_platform.application.resource_management.renew_lease.command import (
    RenewDatabase,
)
from devops_platform.application.resource_management.renew_lease.handler import (
    RenewDatabaseLeaseHandler,
)
from devops_platform.application.resource_management.submit_database_request.command import (
    RequestTemporaryDatabase,
)
from devops_platform.application.resource_management.submit_database_request.handler import (
    RequestTemporaryDatabaseHandler,
)
from devops_platform.application.software_delivery.attach_database.command import AttachDatabase
from devops_platform.application.software_delivery.attach_database.handler import (
    AttachApplicationResourceHandler,
)
from devops_platform.application.software_delivery.create_local_preview.command import (
    CreateLocalPreview,
)
from devops_platform.application.software_delivery.create_local_preview.handler import (
    CreateLocalPreviewHandler,
)
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
)
from devops_platform.application.software_delivery.deploy_application.handler import (
    DeployApplicationHandler,
)
from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.handle_preview_webhook.handler import (
    ProcessGithubPreviewWebhookHandler,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.application.software_delivery.retry_delivery_step.handler import (
    RetryDeliveryStepHandler,
)
from devops_platform.authorization import authorize_platform_action
from shared.dispatch import Command, HandlerRegistry, ModuleDispatcher, Query

ResultT = TypeVar("ResultT")


PLATFORM_HANDLER_REGISTRY = HandlerRegistry(
    commands=(
        (RequestTemporaryDatabase, RequestTemporaryDatabaseHandler),
        (RenewDatabase, RenewDatabaseLeaseHandler),
        (DeleteDatabase, DeleteTemporaryDatabaseHandler),
        (CreateApplication, CreateApplicationHandler),
        (CreateLocalPreview, CreateLocalPreviewHandler),
        (AttachDatabase, AttachApplicationResourceHandler),
        (DeployApplication, DeployApplicationHandler),
        (RetryDeliveryStep, RetryDeliveryStepHandler),
        (ProcessGithubPreviewWebhook, ProcessGithubPreviewWebhookHandler),
    ),
    queries=(
        (ReadCatalog, ReadCatalogQueryHandler),
        (ReadProject, ReadProjectHandler),
        (ReadProjects, ReadProjectsHandler),
        (ReadResources, ReadResourcesHandler),
        (ReadResource, ReadResourceHandler),
        (ReadOperation, ReadOperationHandler),
        (ReadDatabaseConnection, GetDatabaseConnectionQueryHandler),
        (ReadResourceActivity, ListResourceActivityQueryHandler),
        (ReadTemplates, ReadTemplatesHandler),
        (ReadApplications, ReadApplicationsHandler),
        (ReadApplication, ReadApplicationHandler),
        (ReadDeploymentHistory, ReadDeploymentHistoryHandler),
    ),
)


class DeveloperPlatformModuleDispatcher(ModuleDispatcher):
    """Internal handler dispatcher; only authenticated hosts expose the module contract."""

    def __init__(self, resolve_handler: Callable[[type[Any]], Awaitable[Any]]) -> None:
        super().__init__(PLATFORM_HANDLER_REGISTRY, resolve_handler)

    async def execute(self, command: Command[ResultT]) -> ResultT:
        authorize_platform_action(command)
        return await super().execute(command)

    async def query(self, query: Query[ResultT]) -> ResultT:
        authorize_platform_action(query)
        return await super().query(query)
