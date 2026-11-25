from datetime import UTC, datetime

from identity.application.interfaces.security import TokenHasher
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.shared.session_security import (
    authorize_session_operation,
    require_allowed_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository


class RevokeSessionHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        hasher: TokenHasher,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.sessions = sessions
        self.hasher = hasher
        self.allowed_origins = allowed_origins

    async def execute(self, command: RevokeSessionCommand) -> bool:
        require_allowed_origin(command.origin, self.allowed_origins)
        now = datetime.now(UTC)
        principal = await authorize_session_operation(
            self.sessions,
            token_digest=self.hasher.digest(command.session_token),
            project_id=None,
            now=now,
            mutate=True,
            csrf_digest=lambda: self.hasher.digest(command.csrf_token),
        )
        session = await self.sessions.load_for_revocation(principal.user_id, command.session_id)
        if session is None:
            return False
        revoked = session.revoke(now)
        if revoked is session:
            return False
        await self.sessions.save_revocation(revoked)
        return True
