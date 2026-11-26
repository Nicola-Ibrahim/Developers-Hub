"""Revalidate cookie credentials within the protected Identity transaction."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request

from api.core.errors import APIError
from api.identity.authentication.credentials import browser_credentials, require_cookie_session
from identity.application.interfaces.dispatch import ActionPrecondition
from identity.application.interfaces.security import TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal


def browser_write_precondition(
    request: Request, actor_id: UUID, hasher: TokenHasher
) -> ActionPrecondition:
    return _session_precondition(request, actor_id, hasher, verify_csrf=True)


def browser_read_precondition(
    request: Request, actor_id: UUID, hasher: TokenHasher
) -> ActionPrecondition:
    return _session_precondition(request, actor_id, hasher, verify_csrf=False)


def _session_precondition(
    request: Request, actor_id: UUID, hasher: TokenHasher, *, verify_csrf: bool
) -> ActionPrecondition:
    credentials = browser_credentials(request)
    digest = hasher.digest(require_cookie_session(credentials))
    csrf_token = credentials.csrf_token

    async def check(
        sessions: SessionRepository, _tokens: ApiTokenRepository | None
    ) -> SessionPrincipal:
        principal = await sessions.authorize_session_operation(
            digest, None, datetime.now(UTC), lock_for_mutation=verify_csrf
        )
        if (
            principal is None
            or principal.user_id != actor_id
            or (
                verify_csrf
                and (
                    csrf_token is None
                    or not await sessions.validate_csrf(digest, hasher.digest(csrf_token))
                )
            )
        ):
            raise APIError(
                401, "authentication_rejected", "Credentials or browser session are invalid"
            )
        return principal

    return check
