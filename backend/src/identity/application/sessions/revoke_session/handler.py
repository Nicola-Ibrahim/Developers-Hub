from collections.abc import Callable
from datetime import datetime

from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.shared.session_security import (
    DigestSecret,
    authorize_browser_operation,
    require_browser_origin,
)
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.session_revocation_repository import SessionRevocationRepository
from shared.application.interfaces.unit_of_work import UnitOfWork


class RevokeSessionHandler:
    def __init__(
        self,
        authorization: SessionRepository,
        revocations: SessionRevocationRepository,
        unit: UnitOfWork,
        clock: Callable[[], datetime],
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.authorization = authorization
        self.revocations = revocations
        self.unit = unit
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: RevokeSessionCommand) -> bool:
        async def action() -> bool:
            require_browser_origin(command.origin, self.allowed_origins)
            now = self.clock()
            principal = await authorize_browser_operation(
                self.authorization,
                token_digest=self.digest_secret(command.session_token),
                project_id=None,
                now=now,
                mutate=True,
                csrf_digest=lambda: self.digest_secret(command.csrf_token),
            )
            session = await self.revocations.load_for_revocation(
                principal.user_id, command.session_id
            )
            if session is None:
                return False
            revoked = session.revoke(now)
            if revoked is session:
                return False
            await self.revocations.save_revocation(revoked)
            return True

        return await self.unit.run(action, lambda result: result)
