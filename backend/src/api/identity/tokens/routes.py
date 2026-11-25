"""Browser-facing personal token endpoints using Identity dispatch."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field

from api.core.errors import APIError
from api.identity.authentication.credentials import (
    CSRF_HEADER,
    browser_credentials,
    require_cookie_session,
)
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
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
        require_cookie_session(browser_credentials(request)), project_id
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
    module: FromDishka[IdentityModule],
    csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
) -> dict[str, object]:
    result = await module.execute(
        CreatePersonalTokenCommand(
            require_cookie_session(browser_credentials(request)),
            csrf_token,
            request.headers.get("origin"),
            body.name,
            tuple(body.scopes),
            body.hours,
        )
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
    module: FromDishka[IdentityModule],
    csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
) -> dict[str, object]:
    result = await module.execute(
        RotatePersonalTokenCommand(
            require_cookie_session(browser_credentials(request)),
            csrf_token,
            request.headers.get("origin"),
            token_id,
        )
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
    module: FromDishka[IdentityModule],
    csrf_token: Annotated[str, Header(alias=CSRF_HEADER)],
) -> Response:
    revoked = await module.execute(
        RevokePersonalTokenCommand(
            require_cookie_session(browser_credentials(request)),
            csrf_token,
            request.headers.get("origin"),
            token_id,
        )
    )
    if not revoked:
        raise APIError(404, "not_found", "Token not found")
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 204
    return response
