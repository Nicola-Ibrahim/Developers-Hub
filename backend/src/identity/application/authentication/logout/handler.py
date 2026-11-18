from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.logout.command import LogoutCommand
from identity.application.shared.session_security import (
    DigestSecret,
    authorize_browser_operation,
    require_browser_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository
from shared.application.interfaces.unit_of_work import UnitOfWork


class LogoutHandler:
    def __init__(
        self,
        authorization: SessionRepository,
        sessions: SessionRepository,
        unit: UnitOfWork,
        clock: Callable[[], datetime],
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.authorization = authorization
        self.sessions = sessions
        self.unit = unit
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: LogoutCommand) -> None:
        async def action() -> None:
            require_browser_origin(command.origin, self.allowed_origins)
            token_digest = self.digest_secret(command.session_token)
            now = self.clock()
            await authorize_browser_operation(
                self.authorization,
                token_digest=token_digest,
                project_id=None,
                now=now,
                mutate=True,
                csrf_digest=lambda: self.digest_secret(command.csrf_token),
            )
            await self.sessions.logout(token_digest, now)

        await self.unit.run(action, lambda result: result)
