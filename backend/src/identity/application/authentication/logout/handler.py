from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.logout.command import LogoutCommand
from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.shared.session_security import BrowserMutationAuthorizer, DigestSecret


class LogoutHandler:
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

    async def execute(self, command: LogoutCommand) -> None:
        async def action(repository: BrowserRepository) -> None:
            await BrowserMutationAuthorizer(
                repository, self.clock, self.digest_secret, self.allowed_origins
            ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
            await repository.logout(self.digest_secret(command.session_token), self.clock())

        await self.transaction.run(action)
