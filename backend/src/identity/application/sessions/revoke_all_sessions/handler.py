from datetime import UTC, datetime

from identity.application.interfaces.security import TokenHasher
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.shared.session_security import (
    authorize_session_operation,
    require_allowed_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository


class RevokeAllSessionsHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        hasher: TokenHasher,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.sessions = sessions
        self.hasher = hasher
        self.allowed_origins = allowed_origins

    async def execute(self, command: RevokeAllSessionsCommand) -> int:
        require_allowed_origin(command.origin, self.allowed_origins)
        token_digest = self.hasher.digest(command.session_token)
        now = datetime.now(UTC)
        principal = await authorize_session_operation(
            self.sessions,
            token_digest=token_digest,
            project_id=None,
            now=now,
            mutate=True,
            csrf_digest=lambda: self.hasher.digest(command.csrf_token),
        )
        return await self.sessions.logout_all(principal.user_id, now)
