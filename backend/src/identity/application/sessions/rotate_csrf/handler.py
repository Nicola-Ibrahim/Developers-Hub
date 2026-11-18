from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.records import SessionPrincipal

Clock = Callable[[], datetime]

DigestSecret = Callable[[str], str]

GenerateSecret = Callable[[], str]


class RotateCsrfHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        digest_secret: DigestSecret,
        generate_secret: GenerateSecret,
    ) -> None:
        self.transaction = transaction
        self.clock = clock
        self.digest_secret = digest_secret
        self.generate_secret = generate_secret

    async def execute(self, command: RotateCsrfCommand) -> SessionPrincipal:
        return await self.transaction.run(lambda repository: self._execute(repository, command))

    async def _execute(
        self, repository: BrowserRepository, command: RotateCsrfCommand
    ) -> SessionPrincipal:
        csrf = self.generate_secret()
        token_digest = self.digest_secret(command.session_token)
        result = await repository.authenticate_session(
            token_digest=token_digest, project_id=None, now=self.clock()
        )
        if result is None or not await repository.rotate_csrf(
            token_digest, self.digest_secret(csrf), self.clock()
        ):
            raise BrowserAuthenticationRejected()
        return replace(result[0], csrf_token=csrf)
