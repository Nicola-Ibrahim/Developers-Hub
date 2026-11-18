from collections.abc import Callable
from datetime import datetime

from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.shared.session_security import (
    DigestSecret,
    authorize_browser_operation,
    require_browser_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository
from shared.application.interfaces.unit_of_work import UnitOfWork


class RevokeAllSessionsHandler:
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

    async def execute(self, command: RevokeAllSessionsCommand) -> int:
        async def action() -> int:
            require_browser_origin(command.origin, self.allowed_origins)
            token_digest = self.digest_secret(command.session_token)
            now = self.clock()
            principal = await authorize_browser_operation(
                self.authorization,
                token_digest=token_digest,
                project_id=None,
                now=now,
                mutate=True,
                csrf_digest=lambda: self.digest_secret(command.csrf_token),
            )
            return await self.sessions.logout_all(principal.user_id, now)

        return await self.unit.run(action, lambda result: result)
