from datetime import UTC, datetime

from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.list_sessions.result import SessionDetails
from identity.domain.interfaces.session_repository import SessionRepository


class ListSessionsHandler:
    def __init__(self, repository: SessionRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListSessionsQuery) -> tuple[SessionDetails, ...]:
        sessions = await self.repository.list_sessions(
            query.actor_id, query.current_session_id, datetime.now(UTC)
        )
        return tuple(
            SessionDetails(
                session.id,
                session.created_at,
                session.last_seen_at,
                session.expiry.idle_at,
                session.expiry.absolute_at,
                session.id == query.current_session_id,
            )
            for session in sessions
        )
