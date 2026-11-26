"""Compose browser session policy with the request's existing SQL transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
from identity.infra.security.opaque_secrets import PepperedTokenHasher


async def authenticate_browser_operation(
    session: AsyncSession,
    token: str,
    project_id: UUID | None,
    csrf_token: str | None = None,
    mutate: bool = False,
    token_pepper: str = "",
    *,
    project_access: IdentityProjectAccess,
) -> SessionPrincipal:
    digest = PepperedTokenHasher(token_pepper).digest
    users = SQLAlchemyUserRepository(session, project_access)
    sessions = SQLAlchemySessionRepository(session, users, project_access)
    token_digest = digest(token)
    principal = await sessions.authorize_session_operation(
        token_digest, project_id, datetime.now(UTC), lock_for_mutation=mutate
    )
    if principal is None or (
        mutate
        and (
            csrf_token is None or not await sessions.validate_csrf(token_digest, digest(csrf_token))
        )
    ):
        raise SessionAuthenticationRejected()
    return principal
