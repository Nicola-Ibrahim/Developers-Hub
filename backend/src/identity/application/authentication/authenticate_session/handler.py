from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal


async def authenticate_session(
    repository: SessionRepository,
    clock: Callable[[], datetime],
    digest_secret: Callable[[str], str],
    session_token: str,
    project_id: UUID | None = None,
) -> SessionPrincipal:
    result = await repository.authenticate_session(
        token_digest=digest_secret(session_token),
        project_id=project_id,
        now=clock(),
    )
    if result is None:
        raise BrowserAuthenticationRejected()
    return result[0]


class AuthenticateSessionHandler:
    def __init__(
        self,
        repository: SessionRepository,
        clock: Callable[[], datetime],
        digest_secret: Callable[[str], str],
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.digest_secret = digest_secret

    async def execute(self, query: AuthenticateSessionQuery) -> SessionPrincipal:
        return await authenticate_session(
            self.repository,
            self.clock,
            self.digest_secret,
            query.session_token,
            query.project_id,
        )
