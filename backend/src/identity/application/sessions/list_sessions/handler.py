from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.authenticate_session.handler import authenticate_session
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.list_sessions.result import SessionDetails
from identity.domain.interfaces.session_repository import SessionRepository


class ListSessionsHandler:
    def __init__(
        self,
        repository: SessionRepository,
        clock: Callable[[], datetime],
        digest_secret: Callable[[str], str],
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.digest_secret = digest_secret

    async def execute(self, command: ListSessionsQuery) -> tuple[SessionDetails, ...]:
        async def action() -> tuple[SessionDetails, ...]:
            principal = await authenticate_session(
                self.repository, self.clock, self.digest_secret, command.session_token
            )
            sessions = await self.repository.list_sessions(
                principal.user_id, principal.session_id, self.clock()
            )
            return tuple(
                SessionDetails(
                    session.id,
                    session.created_at,
                    session.last_seen_at,
                    session.expiry.idle_at,
                    session.expiry.absolute_at,
                    session.id == principal.session_id,
                )
                for session in sessions
            )

        return await action()
