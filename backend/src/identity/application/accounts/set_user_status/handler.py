from collections.abc import Callable
from datetime import datetime

from identity.application.accounts.set_user_status.command import SetUserStatusCommand
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository

Clock = Callable[[], datetime]


class SetUserStatusHandler:
    def __init__(self, transaction: BrowserTransaction, clock: Clock) -> None:
        self.transaction = transaction
        self.clock = clock

    async def execute(self, command: SetUserStatusCommand) -> None:
        async def update_status(users: UserRepository, sessions: SessionRepository) -> None:
            changed = await users.set_user_active(
                actor_id=command.actor_id,
                user_id=command.user_id,
                active=command.active,
                now=self.clock(),
            )
            if changed and not command.active:
                await sessions.revoke_user_sessions(command.user_id, self.clock())

        await self.transaction.run(update_status)
