"""Browser write preconditions executed inside Identity ACTION transactions."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request

from api.core.errors import APIError
from api.identity.authentication.credentials import browser_credentials, require_cookie_session
from identity.application.interfaces.dispatch import ActionPrecondition, IdentityModule
from identity.application.interfaces.security import TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal


def browser_write_precondition(
    request: Request,
    actor_id: UUID,
    hasher: TokenHasher,
    *,
    token_id: UUID | None = None,
    expected_project_id: UUID | None = None,
    check_project: bool = False,
) -> ActionPrecondition:
    credentials = browser_credentials(request)

    async def check(
        sessions: SessionRepository, tokens: ApiTokenRepository
    ) -> SessionPrincipal:
        if token_id is not None:
            await tokens.lock_personal_token(token_id)
        digest = hasher.digest(require_cookie_session(credentials))
        principal = await sessions.authorize_session_operation(
            digest, None, datetime.now(UTC), lock_for_mutation=True
        )
        csrf = credentials.csrf_token
        if (
            principal is None
            or principal.user_id != actor_id
            or csrf is None
            or not await sessions.validate_csrf(digest, hasher.digest(csrf))
        ):
            raise APIError(
                401,
                "authentication_rejected",
                "Credentials or browser session are invalid",
            )
        if check_project and principal.project_id != expected_project_id:
            raise APIError(
                401,
                "authentication_rejected",
                "Credentials or browser session are invalid",
            )
        return principal

    return check


async def execute_browser_write(module: IdentityModule, command, precondition: ActionPrecondition):
    return await module.execute_with_precondition(command, precondition)
