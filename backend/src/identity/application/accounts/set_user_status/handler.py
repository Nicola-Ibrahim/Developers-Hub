from datetime import UTC, datetime

from identity.application.accounts.set_user_status.command import SetUserStatusCommand
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository


class SetUserStatusHandler:
    def __init__(self, transaction: IdentityTransaction) -> None:
        self.transaction = transaction

    async def execute(self, command: SetUserStatusCommand) -> None:
        async def update_status(users: UserRepository, sessions: SessionRepository) -> None:
            now = datetime.now(UTC)
            changed = await users.set_user_active(
                actor_id=command.actor_id,
                user_id=command.user_id,
                active=command.active,
                now=now,
            )
            if changed and not command.active:
                await sessions.revoke_user_sessions(command.user_id, now)

        await self.transaction.run(update_status)
