"""Browser-only self-service profile and security history."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

from api.composition.identity_preconditions import browser_write_precondition, execute_browser_write
from api.identity.authentication.credentials import (
    CSRF_HEADER,
    browser_credentials,
    require_cookie_session,
)
from api.identity.profile.schemas import ProfileView, SecurityActivityView, UpdateProfileBody
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.security import TokenHasher
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand

router = APIRouter()


@router.get("/me/profile", response_model=ProfileView, tags=["identity"])
@inject
async def get_profile(
    request: Request, response: Response, module: FromDishka[IdentityModule]
) -> ProfileView:
    response.headers["Cache-Control"] = "no-store"
    profile = await module.query(ProfileQuery(require_cookie_session(browser_credentials(request))))
    return ProfileView(
        userId=profile.user_id, userName=profile.user_name, displayName=profile.display_name
    )


@router.patch("/me/profile", response_model=ProfileView, tags=["identity"])
@inject
async def patch_profile(
    body: UpdateProfileBody,
    request: Request,
    response: Response,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    module: FromDishka[IdentityModule],
    hasher: FromDishka[TokenHasher],
) -> ProfileView:
    command = UpdateProfileCommand(
        request.state.identity_principal.user_id,
        body.display_name,
    )
    profile = await execute_browser_write(module, command, browser_write_precondition(
        request, request.state.identity_principal.user_id, hasher
    ))
    response.headers["Cache-Control"] = "no-store"
    return ProfileView(
        userId=profile.user_id, userName=profile.user_name, displayName=profile.display_name
    )


@router.get("/me/security-history", response_model=list[SecurityActivityView], tags=["identity"])
@inject
async def security_history(
    request: Request, response: Response, module: FromDishka[IdentityModule]
) -> list[SecurityActivityView]:
    response.headers["Cache-Control"] = "no-store"
    items = await module.query(
        SecurityHistoryQuery(require_cookie_session(browser_credentials(request)))
    )
    return [
        SecurityActivityView(
            id=item.id, action=item.action, outcome=item.outcome, createdAt=item.created_at
        )
        for item in items
    ]
