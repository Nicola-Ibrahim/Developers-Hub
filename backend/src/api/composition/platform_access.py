"""Revalidate identity credentials and produce trusted platform access."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from api.composition.browser_access import authenticate_browser_operation
from api.core.security.request_identity import BrowserRequestCredentials, RequestIdentity
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import PlatformRequestError
from identity.application.api_tokens.authenticate_api_token.handler import authenticate_api_token
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.security.tokens import PepperedTokenHasher
from shared.infra.settings import Settings


async def authenticate_platform_access(
    session: AsyncSession,
    identity: RequestIdentity,
    settings: Settings,
    clock: Callable[[], datetime],
) -> AccessContext:
    if isinstance(identity, BrowserRequestCredentials):
        principal = await authenticate_browser_operation(
            session,
            identity.session_token,
            identity.project_id,
            clock,
            identity.csrf_token,
            identity.origin,
            settings.browser_allowed_origins,
            identity.mutate,
            settings.token_pepper.get_secret_value(),
        )
        if principal.project_id is None or principal.role not in {"developer", "admin"}:
            raise PlatformRequestError("project_required", "Select an authorized project", 409)
        return AccessContext(
            principal.user_id,
            principal.project_id,
            cast(Literal["developer", "admin"], principal.role),
            frozenset(principal.scopes),
        )
    principal_token = await authenticate_api_token(
        AuthenticateApiTokenQuery(identity),
        SQLAlchemyApiTokenRepository(session),
        PepperedTokenHasher(settings.token_pepper.get_secret_value()),
        clock,
    )
    return AccessContext(
        principal_token.user_id,
        principal_token.project_id,
        principal_token.role,
        principal_token.scopes,
    )
