from collections.abc import Callable
from datetime import datetime

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.shared.session_security import BrowserMutationAuthorizer, DigestSecret


class RevokeSessionHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        clock: Callable[[], datetime],
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.transaction = transaction
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: RevokeSessionCommand) -> bool:
        async def action(repository: BrowserRepository) -> bool:
            principal = await BrowserMutationAuthorizer(
                repository, self.clock, self.digest_secret, self.allowed_origins
            ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
            return await repository.revoke_session(
                principal.user_id, command.session_id, self.clock()
            )

        return await self.transaction.run(action)
