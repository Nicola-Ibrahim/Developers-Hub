"""Personal token handlers with operation-specific dependencies."""

from datetime import UTC, datetime, timedelta

from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.records import ApiTokenAuditEvent, PersonalApiToken
from identity.domain.value_objects.token_scopes import TokenScopes


class PersonalTokenQueryHandler:
    def __init__(self, tokens: ApiTokenRepository) -> None:
        self.tokens = tokens

    async def execute(self, query: ListPersonalTokensQuery) -> tuple[PersonalApiToken, ...]:
        return await self.tokens.list_personal_tokens(query.actor_id, query.project_id)


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
        if command.project_id is None:
            raise IdentityValidationError("Select a project before creating a token")
        if not command.name.strip() or len(command.name) > 100 or not 1 <= command.hours <= 720:
            raise IdentityValidationError("Invalid token name or duration")
        scopes = TokenScopes.select(
            command.scopes, allowed=self.allowed_scopes, defaults=self.allowed_scopes
        ).values
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=command.hours)
        secret = self.generator.generate()
        token_id = await self.tokens.create_personal_token(
            user_id=command.actor_id,
            project_id=command.project_id,
            name=command.name.strip(),
            digest=self.hasher.digest(secret),
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
        )
        await self.tokens.record_token_audit(
            ApiTokenAuditEvent(
                command.actor_id, command.project_id, "token_issued", "succeeded", token_id
            )
        )
        return PersonalApiToken(
            token_id, command.name.strip(), command.project_id, scopes, expires_at, None
        ), secret


class RotatePersonalTokenHandler:
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

    async def execute(
        self, command: RotatePersonalTokenCommand
    ) -> tuple[PersonalApiToken, str] | None:
        locked_token = await self.tokens.lock_personal_token(command.token_id)
        if locked_token is None or locked_token.user_id != command.actor_id:
            return None
        now, secret = datetime.now(UTC), self.generator.generate()
        token = await self.tokens.rotate_personal_token(
            user_id=command.actor_id,
            token_id=command.token_id,
            digest=self.hasher.digest(secret),
            now=now,
            allowed_scopes=self.allowed_scopes,
        )
        if token is None:
            return None
        await self.tokens.record_token_audit(
            ApiTokenAuditEvent(
                command.actor_id, token.project_id, "token_rotated", "succeeded", token.token_id
            )
        )
        return token, secret


class RevokePersonalTokenHandler:
    def __init__(
        self,
        tokens: ApiTokenRepository,
    ) -> None:
        self.tokens = tokens

    async def execute(self, command: RevokePersonalTokenCommand) -> bool:
        locked_token = await self.tokens.lock_personal_token(command.token_id)
        if locked_token is None or locked_token.user_id != command.actor_id:
            return False
        return await self.tokens.revoke_personal_token(
            user_id=command.actor_id,
            token_id=command.token_id,
            now=datetime.now(UTC),
        )
