from dataclasses import replace
from datetime import UTC, datetime

from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected


class SelectActiveProjectHandler:
    def __init__(
        self,
        repository: SessionRepository,
        hasher: TokenHasher,
        generator: TokenGenerator,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.generator = generator

    async def execute(self, command: SelectActiveProjectCommand) -> SessionPrincipal:
        return await self._execute(command)

    async def _execute(self, command: SelectActiveProjectCommand) -> SessionPrincipal:
        csrf = self.generator.generate()
        token_digest = self.hasher.digest(command.session_token)
        principal = await self.repository.select_project(
            token_digest=token_digest,
            project_id=command.project_id,
            now=datetime.now(UTC),
        )
        if principal is None or not await self.repository.rotate_csrf(
            token_digest, self.hasher.digest(csrf), datetime.now(UTC)
        ):
            raise SessionAuthenticationRejected()
        return replace(principal, csrf_token=csrf)
