"""Current-session, session-list and password routes."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

from api.composition.identity_preconditions import (
    browser_read_precondition,
    browser_write_precondition,
)
from api.identity.authentication.credentials import (
    CSRF_HEADER,
    SESSION_COOKIE,
    browser_credentials,
    require_cookie_session,
)
from api.identity.sessions.mapping import _principal
from api.identity.sessions.schemas import PasswordBody
from api.settings.config import BrowserCookiePolicy
from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.security import TokenHasher
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand

router = APIRouter()


@router.get("/me/browser", tags=["identity"])
@inject
async def browser_me(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
    hasher: FromDishka[TokenHasher],
) -> dict[str, object]:
    command = RotateCsrfCommand(require_cookie_session(browser_credentials(request)))
    principal = await module.execute_with_precondition(
        command,
        browser_read_precondition(request, request.state.identity_principal.user_id, hasher),
    )
    response.headers["Cache-Control"] = "no-store"
    return {"csrfToken": principal.csrf_token, "principal": _principal(principal)}


@router.get("/me/sessions", tags=["identity"])
@inject
async def sessions(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
    hasher: FromDishka[TokenHasher],
) -> list[dict[str, object]]:
    response.headers["Cache-Control"] = "no-store"
    actor = request.state.identity_principal
    query = ListSessionsQuery(actor.user_id, actor.session_id)
    values = await module.query_with_precondition(
        query, browser_read_precondition(request, actor.user_id, hasher)
    )
    return [
        {
            "sessionId": str(item.session_id),
            "createdAt": item.created_at.isoformat(),
            "lastSeenAt": item.last_seen_at.isoformat(),
            "idleExpiresAt": item.idle_expires_at.isoformat(),
            "absoluteExpiresAt": item.absolute_expires_at.isoformat(),
            "current": item.current,
        }
        for item in values
    ]


@router.delete("/me/sessions/{session_id}", status_code=204, tags=["identity"])
@inject
async def revoke_session(
    session_id: UUID,
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    response: Response,
    module: FromDishka[IdentityModule],
    hasher: FromDishka[TokenHasher],
) -> Response:
    command = RevokeSessionCommand(
        request.state.identity_principal.user_id,
        session_id,
    )
    await module.execute_with_precondition(
        command,
        browser_write_precondition(request, request.state.identity_principal.user_id, hasher),
    )
    response.status_code = 204
    return response


@router.post("/me/password", status_code=204, tags=["identity"])
@inject
async def change_password(
    body: PasswordBody,
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    response: Response,
    module: FromDishka[IdentityModule],
    cookie_policy: FromDishka[BrowserCookiePolicy],
    hasher: FromDishka[TokenHasher],
) -> Response:
    actor = request.state.identity_principal
    command = ChangePasswordCommand(
        actor.user_id, actor.user_name, body.current_password, body.new_password
    )
    await module.execute_with_precondition(
        command, browser_write_precondition(request, actor.user_id, hasher)
    )
    response.delete_cookie(
        SESSION_COOKIE,
        path="/api/v1",
        secure=cookie_policy.secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response
