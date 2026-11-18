"""Platform action permissions shared by HTTP and non-HTTP hosts.

The API checks before dispatch; the host checks again using authenticated access.
Loaded resource ownership and state remain domain/persistence decisions.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from devops_platform.application.applications.create_application.command import (
    CreateApplication,
)
from devops_platform.application.applications.read_applications.query import (
    ReadApplication,
    ReadApplications,
    ReadDeploymentHistory,
)
from devops_platform.application.applications.read_templates.query import ReadTemplates
from devops_platform.application.project_access.manage_project_membership import (
    ListProjectMembers,
    ManageProjectMembership,
)
from devops_platform.application.resource_management.catalog.query import ReadCatalog
from devops_platform.application.resource_management.delete_database.command import (
    DeleteDatabase,
)
from devops_platform.application.resource_management.read_activity.query import (
    ReadResourceActivity,
)
from devops_platform.application.resource_management.read_connection.query import (
    ReadDatabaseConnection,
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
from devops_platform.application.resource_management.submit_database_request.command import (
    RequestTemporaryDatabase,
)
from devops_platform.application.shared.errors import (
    CatalogForbidden,
    PlatformRequestError,
    resource_not_found,
)
from devops_platform.application.software_delivery.attach_database.command import AttachDatabase
from devops_platform.application.software_delivery.create_local_preview.command import (
    CreateLocalPreview,
)
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
)
from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.domain.value_objects.access_context import AccessContext

ALL_SCOPES = (
    "catalog:read",
    "resources:read",
    "resources:write",
    "connections:read",
)


@dataclass(frozen=True, slots=True)
class ActionPermission:
    scope: str | None
    target: Literal["actor", "project", "request", "memberships", "public"] = "actor"
    delivery: bool = False
    owner_required: bool = False  # Enforced after loading the resource/application.


ACTION_PERMISSIONS: dict[type[object], ActionPermission] = {
    ListProjectMembers: ActionPermission("resources:read", "project"),
    ManageProjectMembership: ActionPermission("resources:write", "project"),
    ReadCatalog: ActionPermission("catalog:read"),
    ReadProject: ActionPermission("resources:read", "project"),
    ReadProjects: ActionPermission("resources:read", "memberships"),
    ReadResources: ActionPermission("resources:read", "project"),
    ReadResource: ActionPermission("resources:read"),
    ReadOperation: ActionPermission("resources:read"),
    ReadDatabaseConnection: ActionPermission("connections:read", owner_required=True),
    ReadResourceActivity: ActionPermission("resources:read", "project"),
    ReadTemplates: ActionPermission(None, "public"),
    ReadApplications: ActionPermission("resources:read", delivery=True),
    ReadApplication: ActionPermission("resources:read", delivery=True),
    ReadDeploymentHistory: ActionPermission("resources:read", delivery=True),
    RequestTemporaryDatabase: ActionPermission("resources:write", "request"),
    RenewDatabase: ActionPermission("resources:write", owner_required=True),
    DeleteDatabase: ActionPermission("resources:write", owner_required=True),
    CreateApplication: ActionPermission("resources:write", delivery=True),
    CreateLocalPreview: ActionPermission("resources:write", delivery=True),
    AttachDatabase: ActionPermission("resources:write", delivery=True, owner_required=True),
    DeployApplication: ActionPermission("resources:write", delivery=True, owner_required=True),
    RetryDeliveryStep: ActionPermission("resources:write", delivery=True, owner_required=True),
    ProcessGithubPreviewWebhook: ActionPermission(None, "public"),
}


def _check_actor(access: AccessContext, project_id: UUID, permission: ActionPermission) -> None:
    if access.project_id != project_id:
        raise resource_not_found()
    if access.role not in {"developer", "admin"} or permission.scope not in access.scopes:
        if permission.delivery:
            raise PlatformRequestError("forbidden", "Application access is not permitted", 403)
        raise CatalogForbidden()


def authorize_platform_access(
    action_type: type[object], access: AccessContext, *, project_id: UUID | None = None
) -> None:
    """Check a trusted actor for a developer action without an HTTP dependency."""
    permission = ACTION_PERMISSIONS.get(action_type)
    if permission is None or permission.target == "public":
        raise TypeError("Action has no developer permission policy")
    _check_actor(access, access.project_id if project_id is None else project_id, permission)


def authorize_platform_action(message: object) -> None:
    """Reject unknown actions and enforce coarse project/role/scope access."""
    permission = ACTION_PERMISSIONS.get(type(message))
    if permission is None:
        raise TypeError("Unregistered platform action")
    if permission.target == "public":
        return
    if permission.target == "memberships":
        assert isinstance(message, ReadProjects)
        for membership_access in message.accesses:
            authorize_platform_access(type(message), membership_access)
        return
    access: AccessContext = message.access  # type: ignore[attr-defined]
    if permission.target == "project":
        project_id = message.project_id  # type: ignore[attr-defined]
    elif permission.target == "request":
        project_id = message.request.project_id  # type: ignore[attr-defined]
    else:
        project_id = access.project_id
    authorize_platform_access(type(message), access, project_id=project_id)
