from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.logout.command import LogoutCommand
from identity.application.shared.session_security import (
    DigestSecret,
    authorize_browser_operation,
    require_browser_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository


class LogoutHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        clock: Callable[[], datetime],
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.sessions = sessions
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: LogoutCommand) -> None:
        require_browser_origin(command.origin, self.allowed_origins)
        token_digest = self.digest_secret(command.session_token)
        now = self.clock()
        await authorize_browser_operation(
            self.sessions,
            token_digest=token_digest,
            project_id=None,
            now=now,
            mutate=True,
            csrf_digest=lambda: self.digest_secret(command.csrf_token),
        )
        await self.sessions.logout(token_digest, now)
