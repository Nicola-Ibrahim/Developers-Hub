"""Token scope vocabulary and trusted authorization input construction."""

from uuid import UUID

from devops_platform.application.projects.list_projects.query import ReadProjects
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.authorization.models import AuthorizationRequest

ALL_SCOPES = (
    "catalog:read",
    "resources:read",
    "resources:write",
    "connections:read",
)


def authorization_facts(
    message: object,
    access: AccessContext | None = None,
    *,
    project_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> AuthorizationRequest:
    """Build the existing subject/resource envelope from authenticated facts."""
    if access is None:
        access = getattr(message, "access", None)
    if access is None and isinstance(message, ReadProjects) and message.accesses:
        access = message.accesses[0]

    cls_module = type(message).__module__
    kind = (
        "applications"
        if ".applications." in cls_module or ".software_delivery." in cls_module
        else "projects"
        if ".projects." in cls_module or ".project_access." in cls_module
        else "resources"
    )
    if project_id is None:
        project_id = getattr(message, "project_id", None)
        request = getattr(message, "request", None)
        if project_id is None and request is not None:
            project_id = getattr(request, "project_id", None)
        if project_id is None and access is not None:
            project_id = access.project_id

    resource_id = next(
        (
            getattr(message, field)
            for field in ("application_id", "resource_id", "operation_id", "project_id")
            if isinstance(getattr(message, field, None), UUID)
        ),
        None,
    )
    return AuthorizationRequest(
        subject_id=access.user_id if access is not None else UUID(int=0),
        action="",
        resource_kind=kind,
        resource_id=resource_id,
        project_id=project_id,
        subject_project_id=access.project_id if access is not None else None,
        role=access.role if access is not None else None,
        scopes=tuple(sorted(access.scopes)) if access is not None else (),
        owner_id=owner_id,
    )
