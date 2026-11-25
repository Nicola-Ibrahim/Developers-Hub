from datetime import UTC, datetime

from identity.application.authentication.authenticate_session.handler import authenticate_session
from identity.application.interfaces.security import TokenHasher
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.list_sessions.result import SessionDetails
from identity.domain.interfaces.session_repository import SessionRepository


class ListSessionsHandler:
    def __init__(
        self,
        repository: SessionRepository,
        hasher: TokenHasher,
    ) -> None:
        self.repository = repository
        self.hasher = hasher

    async def execute(self, command: ListSessionsQuery) -> tuple[SessionDetails, ...]:
        async def action() -> tuple[SessionDetails, ...]:
            principal = await authenticate_session(
                self.repository, self.hasher, command.session_token
            )
            sessions = await self.repository.list_sessions(
                principal.user_id, principal.session_id, datetime.now(UTC)
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
