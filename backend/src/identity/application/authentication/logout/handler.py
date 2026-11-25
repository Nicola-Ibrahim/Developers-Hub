from datetime import UTC, datetime

from identity.application.authentication.logout.command import LogoutCommand
from identity.application.interfaces.security import TokenHasher
from identity.application.shared.session_security import (
    authorize_session_operation,
    require_allowed_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository


class LogoutHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        hasher: TokenHasher,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.sessions = sessions
        self.hasher = hasher
        self.allowed_origins = allowed_origins

    async def execute(self, command: LogoutCommand) -> None:
        require_allowed_origin(command.origin, self.allowed_origins)
        token_digest = self.hasher.digest(command.session_token)
        now = datetime.now(UTC)
        await authorize_session_operation(
            self.sessions,
            token_digest=token_digest,
            project_id=None,
            now=now,
            mutate=True,
            csrf_digest=lambda: self.hasher.digest(command.csrf_token),
        )
        await self.sessions.logout(token_digest, now)
