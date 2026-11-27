"""Private per-request credentials; never included in responses or logs."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.identity.authentication.credentials import (
    BrowserCredentials,
    browser_credentials,
    require_browser_mutation,
    require_browser_origin,
    require_cookie_session,
    require_valid_browser_session,
)
from api.settings.config import BrowserCookiePolicy
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.session_tokens import SessionTokenVerifier
from shared.authorization.credentials import RequestCredentials

type RequestIdentity = str | BrowserCredentials | None
bearer = HTTPBearer(auto_error=False)


@inject
async def request_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session_tokens: FromDishka[SessionTokenVerifier],
    cookie_policy: FromDishka[BrowserCookiePolicy],
    request_credentials: FromDishka[RequestCredentials],
) -> RequestIdentity:
    browser = browser_credentials(request)
    require_valid_browser_session(browser, session_tokens)
    if browser.session_token is not None and browser.mutate:
        require_browser_mutation(request, cookie_policy.allowed_origins)
    if browser.session_token is not None:
        identity: RequestIdentity = browser
    else:
        identity = credentials.credentials if credentials is not None else None
    request_credentials.identity = identity
    return identity


@inject
async def browser_request_identity(
    request: Request,
    session_tokens: FromDishka[SessionTokenVerifier],
    cookie_policy: FromDishka[BrowserCookiePolicy],
    request_credentials: FromDishka[RequestCredentials],
) -> BrowserCredentials:
    """Cookie-only authentication for browser routes with no bearer security scheme."""
    credentials = browser_credentials(request)
    require_cookie_session(credentials)
    require_valid_browser_session(credentials, session_tokens)
    if credentials.mutate:
        require_browser_origin(request, cookie_policy.allowed_origins)
    request_credentials.identity = credentials
    return credentials


@inject
async def authenticated_identity(
    request: Request,
    module: FromDishka[IdentityModule],
    credentials: Annotated[BrowserCredentials, Depends(browser_request_identity)],
) -> None:
    principal = await module.query(
        AuthenticateSessionQuery(
            session_token=require_cookie_session(credentials), project_id=credentials.project_id
        )
    )
    request.state.identity_principal = principal
