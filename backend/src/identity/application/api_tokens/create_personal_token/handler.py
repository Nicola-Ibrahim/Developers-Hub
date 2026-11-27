from datetime import UTC, datetime, timedelta

from identity.application.api_tokens.create_personal_token.command import CreatePersonalTokenCommand
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.records import ApiTokenAuditEvent, PersonalApiToken
from identity.domain.value_objects.token_scopes import TokenScopes


class CreatePersonalTokenHandler:
    def __init__(
        self,
        tokens: ApiTokenRepository,
        hasher: TokenHasher,
        generator: TokenGenerator,
        allowed_scopes: tuple[str, ...],
    ) -> None:
        self.tokens = tokens
        self.hasher, self.generator = hasher, generator
        self.allowed_scopes = allowed_scopes

    async def execute(self, command: CreatePersonalTokenCommand) -> tuple[PersonalApiToken, str]:
        project_id = command.require_project_id()
        scopes = TokenScopes.select(
            command.scopes, allowed=self.allowed_scopes, defaults=self.allowed_scopes
        ).values
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=command.hours)
        secret = self.generator.generate()
        token_id = await self.tokens.create_personal_token(
            user_id=command.actor_id,
            project_id=project_id,
            name=command.name,
            digest=self.hasher.digest(secret),
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
        )
        await self.tokens.record_token_audit(
            ApiTokenAuditEvent(command.actor_id, project_id, "token_issued", "succeeded", token_id)
        )
        return PersonalApiToken(
            token_id, command.name, project_id, scopes, expires_at, None
        ), secret
