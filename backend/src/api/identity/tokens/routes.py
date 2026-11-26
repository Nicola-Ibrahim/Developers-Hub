"""Browser-facing personal token endpoints using Identity dispatch."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field

from api.composition.identity_preconditions import (
    browser_read_precondition,
    browser_write_precondition,
)
from api.core.errors import APIError
from api.identity.authentication.credentials import (
    CSRF_HEADER,
)
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.security import TokenHasher
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
    hasher: FromDishka[TokenHasher],
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
) -> list[dict[str, object]]:
    query = ListPersonalTokensQuery(request.state.identity_principal.user_id, project_id)
    items = await module.query_with_precondition(
        query, browser_read_precondition(request, request.state.identity_principal.user_id, hasher)
    )
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
    hasher: FromDishka[TokenHasher],
) -> dict[str, object]:
    actor = request.state.identity_principal
    command = CreatePersonalTokenCommand(
        actor.user_id, actor.project_id, body.name, tuple(body.scopes), body.hours
    )
    result = await module.execute_with_precondition(
        command,
        browser_write_precondition(request, actor.user_id, hasher),
    )
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
    hasher: FromDishka[TokenHasher],
) -> dict[str, object]:
    actor_id = request.state.identity_principal.user_id
    command = RotatePersonalTokenCommand(actor_id, token_id)
    result = await module.execute_with_precondition(
        command,
        browser_write_precondition(request, actor_id, hasher),
    )
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
    hasher: FromDishka[TokenHasher],
) -> Response:
    actor_id = request.state.identity_principal.user_id
    command = RevokePersonalTokenCommand(actor_id, token_id)
    revoked = await module.execute_with_precondition(
        command,
        browser_write_precondition(request, actor_id, hasher),
    )
    if not revoked:
        raise APIError(404, "not_found", "Token not found")
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 204
    return response
