"""Project membership administration endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

from api.core.security.request_identity import BrowserRequestCredentials
from api.identity.authentication.credentials import CSRF_HEADER, browser_credentials
from api.platform.projects.schemas import MembershipBody
from devops_platform.application.interfaces.module import DeveloperPlatformModule
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.shared.dto import AccessContext
from identity.domain.records import SessionPrincipal

router = APIRouter()


async def project_access(project_id: UUID, request: Request) -> AccessContext:
    credentials = browser_credentials(request)
    if not credentials.session_token:
        from api.core.errors import APIError

        raise APIError(401, "authentication_required", "Browser session is required")
    identity = BrowserRequestCredentials(
        credentials.session_token,
        project_id,
        request.headers.get(CSRF_HEADER),
        request.headers.get("origin"),
        request.method not in {"GET", "HEAD", "OPTIONS"},
    )
    request.state.request_identity = identity
    principal = cast(SessionPrincipal, request.state.identity_principal)
    if principal.role not in {"developer", "admin"}:
        from api.core.errors import APIError

        raise APIError(401, "authentication_required", "Project membership is required")
    access = AccessContext(
        principal.user_id,
        project_id,
        cast(Literal["developer", "admin"], principal.role),
        frozenset(principal.scopes),
    )
    return access


@router.get("/projects/{project_id}/members", tags=["identity"])
@inject
async def list_project_members(
    project_id: UUID,
    request: Request,
    response: Response,
    module: FromDishka[DeveloperPlatformModule],
) -> list[dict[str, object]]:
    access = await project_access(project_id, request)
    response.headers["Cache-Control"] = "no-store"
    members = await module.query(ListProjectMembers(access, project_id))
    return [
        {"userId": str(user_id), "userName": name, "role": role, "active": active}
        for user_id, name, role, active in members
    ]


@router.put("/projects/{project_id}/members/{user_id}", status_code=204, tags=["identity"])
@inject
async def set_project_member(
    project_id: UUID,
    user_id: UUID,
    body: MembershipBody,
    request: Request,
    module: FromDishka[DeveloperPlatformModule],
    _csrf: Annotated[str, Header(alias=CSRF_HEADER)],
) -> Response:
    access = await project_access(project_id, request)
    await module.execute(
        ManageProjectMembership(access, project_id, user_id, body.role, datetime.now(UTC))
    )
    return Response(status_code=204)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204, tags=["identity"])
@inject
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    request: Request,
    module: FromDishka[DeveloperPlatformModule],
    _csrf: Annotated[str, Header(alias=CSRF_HEADER)],
) -> Response:
    access = await project_access(project_id, request)
    await module.execute(
        ManageProjectMembership(access, project_id, user_id, None, datetime.now(UTC))
    )
    return Response(status_code=204)
