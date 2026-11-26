"""Explicit platform message bindings; use-case adapters stay in this context."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from devops_platform.application.applications.create_application.command import (
    CreateApplication,
)
from devops_platform.application.applications.create_application.handler import (
    CreateApplicationHandler,
)
from devops_platform.application.applications.get_application.handler import (
    ReadApplicationHandler,
)
from devops_platform.application.applications.get_application.query import (
    ReadApplication,
)
from devops_platform.application.applications.list_applications.handler import (
    ReadApplicationsHandler,
)
from devops_platform.application.applications.list_applications.query import (
    ReadApplications,
)
from devops_platform.application.applications.read_templates.handler import (
    ReadTemplatesHandler,
)
from devops_platform.application.applications.read_templates.query import ReadTemplates
from devops_platform.application.project_access.list_project_members.handler import (
    ListProjectMembersHandler,
)
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.project_access.manage_project_membership.handler import (
    ManageProjectMembershipHandler,
)
from devops_platform.application.projects.get_project.handler import (
    ReadProjectHandler,
)
from devops_platform.application.projects.get_project.query import (
    ReadProject,
)
from devops_platform.application.projects.list_projects.handler import (
    ReadProjectsHandler,
)
from devops_platform.application.projects.list_projects.query import (
    ReadProjects,
)
from devops_platform.application.resource_management.catalog.handler import ReadCatalogQueryHandler
from devops_platform.application.resource_management.catalog.query import ReadCatalog
from devops_platform.application.resource_management.delete_database.command import (
    DeleteDatabase,
)
from devops_platform.application.resource_management.delete_database.handler import (
    DeleteTemporaryDatabaseHandler,
)
from devops_platform.application.resource_management.get_operation.handler import (
    ReadOperationHandler,
)
from devops_platform.application.resource_management.get_operation.query import (
    ReadOperation,
)
from devops_platform.application.resource_management.get_resource.handler import (
    ReadResourceHandler,
)
from devops_platform.application.resource_management.get_resource.query import (
    ReadResource,
)
from devops_platform.application.resource_management.list_resources.handler import (
    ReadResourcesHandler,
)
from devops_platform.application.resource_management.list_resources.query import (
    ReadResources,
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
from devops_platform.application.software_delivery.read_deployment_history.handler import (
    ReadDeploymentHistoryHandler,
)
from devops_platform.application.software_delivery.read_deployment_history.query import (
    ReadDeploymentHistory,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.application.software_delivery.retry_delivery_step.handler import (
    RetryDeliveryStepHandler,
)
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
        (ManageProjectMembership, ManageProjectMembershipHandler),
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
        (ListProjectMembers, ListProjectMembersHandler),
    ),
)


class DeveloperPlatformModuleDispatcher(ModuleDispatcher):
    """Internal handler dispatcher; only authenticated hosts expose the module contract."""

    def __init__(self, resolve_handler: Callable[[type[Any]], Awaitable[Any]]) -> None:
        super().__init__(PLATFORM_HANDLER_REGISTRY, resolve_handler)

    async def execute(self, command: Command[ResultT]) -> ResultT:
        return await super().execute(command)

    async def query(self, query: Query[ResultT]) -> ResultT:
        return await super().query(query)
