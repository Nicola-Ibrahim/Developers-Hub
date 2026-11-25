"""Compose browser session policy with the request's existing SQL transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.shared.session_security import (
    authorize_session_operation as apply_browser_policy,
)
from identity.application.shared.session_security import (
    require_allowed_origin,
)
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.records import SessionPrincipal
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
from identity.infra.security.opaque_secrets import PepperedTokenHasher


async def authenticate_browser_operation(
    session: AsyncSession,
    token: str,
    project_id: UUID | None,
    csrf_token: str | None = None,
    origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    mutate: bool = False,
    token_pepper: str = "",
    *,
    project_access: IdentityProjectAccess,
) -> SessionPrincipal:
    if mutate:
        require_allowed_origin(origin, allowed_origins)
    digest = PepperedTokenHasher(token_pepper).digest
    users = SQLAlchemyUserRepository(session, project_access)
    sessions = SQLAlchemySessionRepository(session, users, project_access)
    return await apply_browser_policy(
        sessions,
        token_digest=digest(token),
        project_id=project_id,
        now=datetime.now(UTC),
        mutate=mutate,
        csrf_digest=lambda: digest(csrf_token) if csrf_token is not None else None,
    )
