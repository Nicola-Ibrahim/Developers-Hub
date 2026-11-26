"""Project membership administration endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, Header, Response

from api.core.security.request_identity import browser_request_identity
from api.identity.authentication.credentials import (
    CSRF_HEADER,
    BrowserCredentials,
    require_cookie_session,
)
from api.platform.projects.schemas import MembershipBody
from devops_platform.application.interfaces.module import DeveloperPlatformModule
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.shared.dto import AccessContext
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.interfaces.dispatch import IdentityModule
from identity.domain.session_errors import SessionAuthenticationRejected

router = APIRouter()


BrowserIdentity = Annotated[BrowserCredentials, Depends(browser_request_identity)]


async def _member_access(
    credentials: BrowserCredentials,
    identity: IdentityModule,
    project_id: UUID,
    csrf_token: str | None = None,
) -> AccessContext:
    principal = await identity.query(
        AuthenticateSessionQuery(require_cookie_session(credentials), project_id, csrf_token)
    )
    if principal.project_id != project_id or principal.role not in {"developer", "admin"}:
        raise SessionAuthenticationRejected()
    return AccessContext(
        principal.user_id,
        project_id,
        cast(Literal["developer", "admin"], principal.role),
        frozenset(principal.scopes),
    )


@inject
async def member_access(
    project_id: UUID,
    credentials: BrowserIdentity,
    identity: FromDishka[IdentityModule],
) -> AccessContext:
    return await _member_access(credentials, identity, project_id)


@inject
async def member_write_access(
    project_id: UUID,
    credentials: BrowserIdentity,
    identity: FromDishka[IdentityModule],
    csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
) -> AccessContext:
    return await _member_access(credentials, identity, project_id, csrf_token)


@router.get("/projects/{project_id}/members", tags=["identity"])
@inject
async def list_project_members(
    project_id: UUID,
    response: Response,
    access: Annotated[AccessContext, Depends(member_access)],
    module: FromDishka[DeveloperPlatformModule],
) -> list[dict[str, object]]:
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
    access: Annotated[AccessContext, Depends(member_write_access)],
    module: FromDishka[DeveloperPlatformModule],
) -> Response:
    await module.execute(
        ManageProjectMembership(access, project_id, user_id, body.role, datetime.now(UTC))
    )
    return Response(status_code=204)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204, tags=["identity"])
@inject
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    access: Annotated[AccessContext, Depends(member_write_access)],
    module: FromDishka[DeveloperPlatformModule],
) -> Response:
    await module.execute(
        ManageProjectMembership(access, project_id, user_id, None, datetime.now(UTC))
    )
    return Response(status_code=204)
