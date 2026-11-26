"""Browser login, project selection and logout routes."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

from api.core.errors import APIError
from api.identity.authentication.credentials import (
    CSRF_HEADER,
    SESSION_COOKIE,
    browser_credentials,
    require_browser_origin,
    require_cookie_session,
)
from api.identity.authentication.login_rate_limit import login_request_rate_limiter
from api.identity.authentication.schemas import LoginBody, ProjectBody
from api.identity.sessions.mapping import _principal
from api.settings.config import BrowserCookiePolicy
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)

public_router = APIRouter()
router = APIRouter()


@public_router.post("/auth/login", tags=["identity"])
@inject
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
    cookie_policy: FromDishka[BrowserCookiePolicy],
) -> dict[str, object]:
    require_browser_origin(request, cookie_policy.allowed_origins)
    peer = request.client.host if request.client is not None else None
    with login_request_rate_limiter.admit(peer) as allowed:
        if not allowed:
            raise APIError(429, "login_rate_limited", "Too many login requests. Try again later.")
        result = await module.execute(LoginCommand(body.user_name, body.password, body.project_id))
    response.set_cookie(
        SESSION_COOKIE,
        result.session_token,
        httponly=True,
        secure=cookie_policy.secure,
        samesite="lax",
        path="/api/v1",
        max_age=8 * 60 * 60,
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "csrfToken": result.csrf_token,
        "principal": _principal(result.principal),
        "absoluteExpiresAt": result.absolute_expires_at.isoformat(),
    }


@router.post("/auth/project", tags=["identity"])
@inject
async def select_project(
    body: ProjectBody,
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    module: FromDishka[IdentityModule],
) -> dict[str, object]:
    command = SelectActiveProjectCommand(
        require_cookie_session(browser_credentials(request)),
        body.project_id,
    )
    principal = await module.execute(command)
    return {"csrfToken": principal.csrf_token, "principal": _principal(principal)}


@router.post("/auth/logout", status_code=204, tags=["identity"])
@inject
async def logout(
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    response: Response,
    cookie_policy: FromDishka[BrowserCookiePolicy],
    module: FromDishka[IdentityModule],
) -> Response:
    command = LogoutCommand(
        require_cookie_session(browser_credentials(request)),
    )
    await module.execute(command)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/api/v1",
        secure=cookie_policy.secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response


@router.post("/auth/logout-all", tags=["identity"])
@inject
async def logout_all(
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    response: Response,
    cookie_policy: FromDishka[BrowserCookiePolicy],
    module: FromDishka[IdentityModule],
) -> dict[str, int]:
    command = RevokeAllSessionsCommand(request.state.identity_principal.user_id)
    count = await module.execute(command)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/api/v1",
        secure=cookie_policy.secure,
        httponly=True,
        samesite="lax",
    )
    return {"revoked": count}
