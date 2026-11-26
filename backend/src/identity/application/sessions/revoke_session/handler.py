from datetime import UTC, datetime

from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.domain.interfaces.session_repository import SessionRepository


class RevokeSessionHandler:
    def __init__(
        self,
        sessions: SessionRepository,
    ) -> None:
        self.sessions = sessions

    async def execute(self, command: RevokeSessionCommand) -> bool:
        now = datetime.now(UTC)
        session = await self.sessions.load_for_revocation(command.actor_id, command.session_id)
        if session is None:
            return False
        revoked = session.revoke(now)
        if revoked is session:
            return False
        await self.sessions.save_revocation(revoked)
        return True
