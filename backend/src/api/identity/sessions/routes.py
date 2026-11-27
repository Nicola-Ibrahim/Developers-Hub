"""Current-session, session-list and password routes."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

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
) -> dict[str, object]:
    command = RotateCsrfCommand(session_token=require_cookie_session(browser_credentials(request)))
    principal = await module.execute(command)
    response.headers["Cache-Control"] = "no-store"
    return {"csrfToken": principal.csrf_token, "principal": _principal(principal)}


@router.get("/me/sessions", tags=["identity"])
@inject
async def sessions(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
) -> list[dict[str, object]]:
    response.headers["Cache-Control"] = "no-store"
    actor = request.state.identity_principal
    query = ListSessionsQuery(actor_id=actor.user_id, current_session_id=actor.session_id)
    values = await module.query(query)
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
) -> Response:
    command = RevokeSessionCommand(
        actor_id=request.state.identity_principal.user_id,
        session_id=session_id,
    )
    await module.execute(command)
    response.status_code = 204
    return response


@router.post("/me/password", status_code=204, tags=["identity"])
@inject
async def change_password(
    body: PasswordBody,
    request: Request,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    response: Response,
    cookie_policy: FromDishka[BrowserCookiePolicy],
    module: FromDishka[IdentityModule],
) -> Response:
    actor = request.state.identity_principal
    command = ChangePasswordCommand(
        actor_id=actor.user_id,
        actor_name=actor.user_name,
        current_password=body.current_password,
        new_password=body.new_password,
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
