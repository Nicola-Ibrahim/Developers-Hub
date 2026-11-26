from datetime import UTC, datetime
from uuid import UUID

from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.interfaces.security import TokenHasher
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected


async def authenticate_session(
    repository: SessionRepository,
    hasher: TokenHasher,
    session_token: str,
    project_id: UUID | None = None,
) -> SessionPrincipal:
    result = await repository.authenticate_session(
        token_digest=hasher.digest(session_token),
        project_id=project_id,
        now=datetime.now(UTC),
    )
    if result is None:
        raise SessionAuthenticationRejected()
    return result[0]


class AuthenticateSessionHandler:
    def __init__(
        self,
        repository: SessionRepository,
        hasher: TokenHasher,
    ) -> None:
        self.repository = repository
        self.hasher = hasher

    async def execute(self, query: AuthenticateSessionQuery) -> SessionPrincipal:
        if query.csrf_token is not None:
            digest = self.hasher.digest(query.session_token)
            principal = await self.repository.authorize_session_operation(
                digest, query.project_id, datetime.now(UTC), lock_for_mutation=True
            )
            if principal is None or not await self.repository.validate_csrf(
                digest, self.hasher.digest(query.csrf_token)
            ):
                raise SessionAuthenticationRejected()
            return principal

        return await authenticate_session(
            self.repository,
            self.hasher,
            query.session_token,
            query.project_id,
        )
