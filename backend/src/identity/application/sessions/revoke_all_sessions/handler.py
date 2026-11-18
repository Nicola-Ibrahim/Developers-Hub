from collections.abc import Callable
from datetime import datetime

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.shared.session_security import BrowserMutationAuthorizer, DigestSecret


class RevokeAllSessionsHandler:
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

    async def execute(self, command: RevokeAllSessionsCommand) -> int:
        async def action(repository: BrowserRepository) -> int:
            principal = await BrowserMutationAuthorizer(
                repository, self.clock, self.digest_secret, self.allowed_origins
            ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
            return await repository.logout_all(principal.user_id, self.clock())

        return await self.transaction.run(action)
