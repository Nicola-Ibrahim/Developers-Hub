from datetime import UTC, datetime

from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.domain.interfaces.session_repository import SessionRepository


class RevokeAllSessionsHandler:
    def __init__(
        self,
        sessions: SessionRepository,
    ) -> None:
        self.sessions = sessions

    async def execute(self, command: RevokeAllSessionsCommand) -> int:
        now = datetime.now(UTC)
        return await self.sessions.logout_all(command.actor_id, now)
