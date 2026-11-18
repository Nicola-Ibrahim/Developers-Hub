from collections.abc import Callable
from datetime import datetime

from identity.application.api_tokens.revoke_api_token.command import RevokeApiTokenCommand
from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.records import ApiTokenAuditEvent


class RevokeApiTokenHandler:
    def __init__(self, transaction: ApiTokenTransaction, clock: Callable[[], datetime]) -> None:
        self.transaction = transaction
        self.clock = clock

    async def execute(self, command: RevokeApiTokenCommand) -> bool:
        return await self.transaction.run(lambda repository: self._revoke(repository, command))

    async def _revoke(self, repository: ApiTokenRepository, command: RevokeApiTokenCommand) -> bool:
        token_id = command.token_id
        token = await repository.find_api_token(token_id)
        if token is None:
            return False
        if token.revoked_at is None:
            revoked_at = self.clock()
            await repository.revoke_api_token(token_id, revoked_at)
            await repository.record_token_audit(
                ApiTokenAuditEvent(
                    actor_id=token.user_id,
                    project_id=token.project_id,
                    action="token_revoked",
                    outcome="succeeded",
                    request_id=token.token_id,
                )
            )
        return True
