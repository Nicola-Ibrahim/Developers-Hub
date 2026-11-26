"""Revalidate request credentials for Platform operations within their transaction."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import PlatformRequestError
from identity.application.api_tokens.authenticate_api_token.handler import authenticate_api_token
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
from identity.infra.security.opaque_secrets import PepperedTokenHasher
from shared.authorization.credentials import SessionCredentials
from shared.infra.settings import Settings


async def authenticate_browser_operation(
    session: AsyncSession,
    credentials: SessionCredentials,
    project_id: UUID | None,
    *,
    token_pepper: str,
    project_access: IdentityProjectAccess,
) -> SessionPrincipal:
    digest = PepperedTokenHasher(token_pepper).digest
    users = SQLAlchemyUserRepository(session, project_access)
    sessions = SQLAlchemySessionRepository(session, users, project_access)
    if credentials.session_token is None:
        raise SessionAuthenticationRejected()
    token_digest = digest(credentials.session_token)
    principal = await sessions.authorize_session_operation(
        token_digest, project_id, datetime.now(UTC), lock_for_mutation=credentials.mutate
    )
    if principal is None or (
        credentials.mutate
        and (
            credentials.csrf_token is None
            or not await sessions.validate_csrf(token_digest, digest(credentials.csrf_token))
        )
    ):
        raise SessionAuthenticationRejected()
    return principal


async def authenticate_platform_access(
    session: AsyncSession,
    identity: str | SessionCredentials | None,
    settings: Settings,
    project_access: IdentityProjectAccess,
) -> AccessContext:
    if isinstance(identity, SessionCredentials):
        principal = await authenticate_browser_operation(
            session,
            identity,
            identity.project_id,
            token_pepper=settings.token_pepper.get_secret_value(),
            project_access=project_access,
        )
        if principal.project_id is None or principal.role not in {"developer", "admin"}:
            raise PlatformRequestError("project_required", "Select an authorized project", 409)
        return AccessContext(
            principal.user_id,
            principal.project_id,
            cast(Literal["developer", "admin"], principal.role),
            frozenset(principal.scopes),
        )
    if identity is None:
        raise SessionAuthenticationRejected()
    principal_token = await authenticate_api_token(
        AuthenticateApiTokenQuery(identity),
        SQLAlchemyApiTokenRepository(session, project_access),
        PepperedTokenHasher(settings.token_pepper.get_secret_value()),
        datetime.now(UTC),
    )
    return AccessContext(
        principal_token.user_id,
        principal_token.project_id,
        principal_token.role,
        principal_token.scopes,
    )
