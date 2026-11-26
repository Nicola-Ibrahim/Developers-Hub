from datetime import UTC, datetime

from identity.application.authentication.logout.command import LogoutCommand
from identity.application.interfaces.security import TokenHasher
from identity.domain.interfaces.session_repository import SessionRepository


class LogoutHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        hasher: TokenHasher,
    ) -> None:
        self.sessions = sessions
        self.hasher = hasher

    async def execute(self, command: LogoutCommand) -> None:
        token_digest = self.hasher.digest(command.session_token)
        now = datetime.now(UTC)
        await self.sessions.logout(token_digest, now)
