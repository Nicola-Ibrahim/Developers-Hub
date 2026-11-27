from datetime import UTC, datetime

from identity.application.api_tokens.revoke_personal_token.command import RevokePersonalTokenCommand
from identity.domain.interfaces.api_token_repository import ApiTokenRepository


class RevokePersonalTokenHandler:
    def __init__(self, tokens: ApiTokenRepository) -> None:
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
