from datetime import UTC, datetime

from identity.application.api_tokens.rotate_personal_token.command import RotatePersonalTokenCommand
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.records import ApiTokenAuditEvent, PersonalApiToken


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
