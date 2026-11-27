"""Browser-only self-service profile and security history."""

from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Request, Response

from api.identity.authentication.credentials import (
    CSRF_HEADER,
)
from api.identity.profile.schemas import ProfileView, SecurityActivityView, UpdateProfileBody
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.profile.read_profile.query import ProfileQuery
from identity.application.profile.security_history.query import SecurityHistoryQuery
from identity.application.profile.update_profile.command import UpdateProfileCommand

router = APIRouter()


@router.get("/me/profile", response_model=ProfileView, tags=["identity"])
@inject
async def get_profile(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
) -> ProfileView:
    response.headers["Cache-Control"] = "no-store"
    actor = request.state.identity_principal
    query = ProfileQuery(actor_id=actor.user_id)
    profile = await module.query(query)
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
) -> ProfileView:
    command = UpdateProfileCommand(
        actor_id=request.state.identity_principal.user_id,
        display_name=body.display_name,
    )
    profile = await module.execute(command)
    response.headers["Cache-Control"] = "no-store"
    return ProfileView(
        userId=profile.user_id, userName=profile.user_name, displayName=profile.display_name
    )


@router.get("/me/security-history", response_model=list[SecurityActivityView], tags=["identity"])
@inject
async def security_history(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
) -> list[SecurityActivityView]:
    response.headers["Cache-Control"] = "no-store"
    principal = request.state.identity_principal
    query = SecurityHistoryQuery(actor_id=principal.user_id)
    items = await module.query(query)
    return [
        SecurityActivityView(
            id=item.id, action=item.action, outcome=item.outcome, createdAt=item.created_at
        )
        for item in items
    ]
