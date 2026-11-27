"""Browser-facing personal token endpoints using Identity dispatch."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field

from api.core.errors import APIError
from api.identity.authentication.credentials import (
    CSRF_HEADER,
)
from identity.application.api_tokens.create_personal_token.command import CreatePersonalTokenCommand
from identity.application.api_tokens.list_personal_tokens.query import ListPersonalTokensQuery
from identity.application.api_tokens.revoke_personal_token.command import RevokePersonalTokenCommand
from identity.application.api_tokens.rotate_personal_token.command import RotatePersonalTokenCommand
from identity.application.interfaces.dispatch import IdentityModule
from identity.domain.records import PersonalApiToken

router = APIRouter()


class CreateTokenBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str]
    hours: int = Field(ge=1, le=720)


def _view(item: PersonalApiToken) -> dict[str, object]:
    return {
        "id": str(item.token_id),
        "name": item.name,
        "projectId": str(item.project_id),
        "scopes": list(item.scopes),
        "expiresAt": item.expires_at.isoformat(),
        "revokedAt": item.revoked_at.isoformat() if item.revoked_at else None,
    }


@router.get("/me/tokens", tags=["identity"])
@inject
async def list_tokens(
    request: Request,
    response: Response,
    module: FromDishka[IdentityModule],
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
) -> list[dict[str, object]]:
    query = ListPersonalTokensQuery(
        actor_id=request.state.identity_principal.user_id, project_id=project_id
    )
    items = await module.query(query)
    response.headers["Cache-Control"] = "no-store"
    return [_view(item) for item in items]


@router.post("/me/tokens", tags=["identity"])
@inject
async def create_token(
    body: CreateTokenBody,
    request: Request,
    response: Response,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    module: FromDishka[IdentityModule],
) -> dict[str, object]:
    actor = request.state.identity_principal
    command = CreatePersonalTokenCommand(
        actor_id=actor.user_id,
        project_id=actor.project_id,
        name=body.name,
        scopes=tuple(body.scopes),
        hours=body.hours,
    )
    result = await module.execute(command)
    item, secret = result
    response.headers["Cache-Control"] = "no-store"
    return {**_view(item), "secret": secret}


@router.post("/me/tokens/{token_id}/rotate", tags=["identity"])
@inject
async def rotate_token(
    token_id: UUID,
    request: Request,
    response: Response,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    module: FromDishka[IdentityModule],
) -> dict[str, object]:
    actor_id = request.state.identity_principal.user_id
    command = RotatePersonalTokenCommand(actor_id=actor_id, token_id=token_id)
    result = await module.execute(command)
    if result is None:
        raise APIError(404, "not_found", "Token not found")
    item, secret = result
    response.headers["Cache-Control"] = "no-store"
    return {**_view(item), "secret": secret}


@router.delete("/me/tokens/{token_id}", status_code=204, tags=["identity"])
@inject
async def revoke_token(
    token_id: UUID,
    request: Request,
    response: Response,
    _csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
    module: FromDishka[IdentityModule],
) -> Response:
    actor_id = request.state.identity_principal.user_id
    command = RevokePersonalTokenCommand(actor_id=actor_id, token_id=token_id)
    revoked = await module.execute(command)
    if not revoked:
        raise APIError(404, "not_found", "Token not found")
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 204
    return response
