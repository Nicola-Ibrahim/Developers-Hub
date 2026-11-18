"""Compose browser session policy with the request's existing SQL transaction."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.shared.session_security import (
    authorize_browser_operation as apply_browser_policy,
)
from identity.application.shared.session_security import (
    require_browser_origin,
)
from identity.domain.records import SessionPrincipal
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository
from identity.infra.security.tokens import PepperedTokenHasher
from shared.infra.clock import Clock


async def authenticate_browser_operation(
    session: AsyncSession,
    token: str,
    project_id: UUID | None,
    clock: Clock,
    csrf_token: str | None = None,
    origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    mutate: bool = False,
    token_pepper: str = "",
) -> SessionPrincipal:
    if mutate:
        require_browser_origin(origin, allowed_origins)
    digest = PepperedTokenHasher(token_pepper).digest
    return await apply_browser_policy(
        SQLAlchemyIdentityRepository(session),
        token_digest=digest(token),
        project_id=project_id,
        now=clock(),
        mutate=mutate,
        csrf_digest=lambda: digest(csrf_token) if csrf_token is not None else None,
    )
