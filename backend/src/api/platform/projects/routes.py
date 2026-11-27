"""Project registration and metadata routes."""

from dataclasses import asdict
from typing import Annotated, Literal, cast
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends

from api.core.dependencies import platform_access
from api.core.security.request_identity import (
    RequestIdentity,
    request_identity,
)
from api.identity.authentication.credentials import BrowserCredentials, require_cookie_session
from api.platform.projects.memberships import router as memberships_router
from api.platform.projects.schemas import ProjectRegistrationView
from devops_platform.application.interfaces.module import DeveloperPlatformModule
from devops_platform.application.projects.get_project.query import (
    ReadProject,
)
from devops_platform.application.projects.list_projects.query import (
    ReadProjects,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.authorization import ALL_SCOPES
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.interfaces.dispatch import IdentityModule

router = APIRouter()
Access = Annotated[AccessContext, Depends(platform_access)]
Bearer = Annotated[RequestIdentity, Depends(request_identity)]


@router.get("/projects/{project_id}", response_model=ProjectRegistrationView, tags=["projects"])
@inject
async def project(
    project_id: UUID, access: Access, module: FromDishka[DeveloperPlatformModule]
) -> ProjectRegistrationView:
    message = ReadProject(access=access, project_id=project_id)
    result = await module.query(message)
    return ProjectRegistrationView.model_validate(asdict(result))


@router.get("/projects", response_model=list[ProjectRegistrationView], tags=["projects"])
@inject
async def projects(
    credentials: Bearer,
    identity: FromDishka[IdentityModule],
    module: FromDishka[DeveloperPlatformModule],
) -> list[ProjectRegistrationView]:
    if isinstance(credentials, BrowserCredentials):
        principal = await identity.query(
            AuthenticateSessionQuery(session_token=require_cookie_session(credentials))
        )
        user_id = principal.user_id
        accesses = tuple(
            AccessContext(
                principal.user_id,
                member.project_id,
                cast(Literal["developer", "admin"], member.role),
                frozenset(ALL_SCOPES),
            )
            for member in principal.memberships
            if member.role in {"developer", "admin"}
        )
    else:
        token_principal = await identity.query(AuthenticateApiTokenQuery(token=credentials))
        user_id = token_principal.user_id
        accesses = (
            AccessContext(
                token_principal.user_id,
                token_principal.project_id,
                token_principal.role,
                token_principal.scopes,
            ),
        )
    message = ReadProjects(user_id=user_id, accesses=accesses)
    rows = await module.query(message)
    return [ProjectRegistrationView.model_validate(asdict(row)) for row in rows]


router.include_router(memberships_router)
