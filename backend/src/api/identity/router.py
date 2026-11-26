"""Identity HTTP router assembled from feature routers."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, Request

from api.core.security.request_identity import browser_request_identity
from api.identity.authentication.credentials import (
    BrowserCredentials,
    require_cookie_session,
)
from api.identity.authentication.routes import public_router as public_authentication_router
from api.identity.authentication.routes import router as authentication_router
from api.identity.principal.routes import router as principal_router
from api.identity.profile.routes import router as profile_router
from api.identity.sessions.routes import router as sessions_router
from api.identity.tokens.routes import router as tokens_router
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.interfaces.dispatch import IdentityModule


@inject
async def authenticated_identity(
    request: Request,
    module: FromDishka[IdentityModule],
    credentials: Annotated[BrowserCredentials, Depends(browser_request_identity)],
) -> None:
    principal = await module.query(
        AuthenticateSessionQuery(require_cookie_session(credentials), credentials.project_id)
    )
    request.state.identity_principal = principal


router = APIRouter(prefix="/api/v1")
router.include_router(public_authentication_router)
for feature_router in (
    authentication_router,
    sessions_router,
    profile_router,
    tokens_router,
):
    router.include_router(feature_router, dependencies=[Depends(authenticated_identity)])
router.include_router(principal_router)
