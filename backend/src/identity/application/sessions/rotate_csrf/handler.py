from dataclasses import replace
from datetime import UTC, datetime

from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected


class RotateCsrfHandler:
    def __init__(
        self,
        repository: SessionRepository,
        hasher: TokenHasher,
        generator: TokenGenerator,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.generator = generator

    async def execute(self, command: RotateCsrfCommand) -> SessionPrincipal:
        return await self._execute(command)

    async def _execute(self, command: RotateCsrfCommand) -> SessionPrincipal:
        csrf = self.generator.generate()
        token_digest = self.hasher.digest(command.session_token)
        result = await self.repository.authenticate_session(
            token_digest=token_digest, project_id=None, now=datetime.now(UTC)
        )
        if result is None or not await self.repository.rotate_csrf(
            token_digest, self.hasher.digest(csrf), datetime.now(UTC)
        ):
            raise SessionAuthenticationRejected()
        return replace(result[0], csrf_token=csrf)
