"""Private per-request credentials; never included in responses or logs."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.identity.authentication.credentials import (
    BrowserCredentials,
    browser_credentials,
    require_valid_browser_session,
)
from identity.application.interfaces.session_tokens import SessionTokenVerifier

type RequestIdentity = str | BrowserCredentials | None
bearer = HTTPBearer(auto_error=False)


@inject
async def request_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session_tokens: FromDishka[SessionTokenVerifier],
) -> RequestIdentity:
    browser = browser_credentials(request)
    require_valid_browser_session(browser, session_tokens)
    if browser.session_token is not None:
        identity: RequestIdentity = browser
    else:
        identity = credentials.credentials if credentials is not None else None
    request.state.request_identity = identity
    return identity
