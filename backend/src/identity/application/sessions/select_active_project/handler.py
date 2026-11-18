from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)
from identity.application.shared.session_security import BrowserMutationAuthorizer
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.records import SessionPrincipal

Clock = Callable[[], datetime]

DigestSecret = Callable[[str], str]

GenerateSecret = Callable[[], str]


class SelectActiveProjectHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        digest_secret: DigestSecret,
        generate_secret: GenerateSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.transaction = transaction
        self.clock = clock
        self.digest_secret = digest_secret
        self.generate_secret = generate_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: SelectActiveProjectCommand) -> SessionPrincipal:
        return await self.transaction.run(lambda repository: self._execute(repository, command))

    async def _execute(
        self, repository: BrowserRepository, command: SelectActiveProjectCommand
    ) -> SessionPrincipal:
        await BrowserMutationAuthorizer(
            repository, self.clock, self.digest_secret, self.allowed_origins
        ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
        csrf = self.generate_secret()
        token_digest = self.digest_secret(command.session_token)
        principal = await repository.select_project(
            token_digest=token_digest, project_id=command.project_id, now=self.clock()
        )
        if principal is None or not await repository.rotate_csrf(
            token_digest, self.digest_secret(csrf), self.clock()
        ):
            raise BrowserAuthenticationRejected()
        return replace(principal, csrf_token=csrf)
